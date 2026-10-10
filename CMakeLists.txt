cmake_minimum_required(VERSION 3.22)
project(winky VERSION 0.11.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 11)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()

# Härtung wie bei Ubuntu-Paketen üblich
add_compile_options(-Wall -Wextra -Wformat=2 -fstack-protector-strong
                    -fstack-clash-protection -fcf-protection -D_FORTIFY_SOURCE=3)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
add_link_options(-Wl,-z,relro,-z,now -Wl,--as-needed)

find_package(PkgConfig REQUIRED)
pkg_check_modules(SYSTEMD REQUIRED IMPORTED_TARGET libsystemd)

# ONNX Runtime liegt geprüft in vendor/ (scripts/abhaengigkeiten.sh)
set(ORT_ROOT "${CMAKE_SOURCE_DIR}/vendor/onnxruntime" CACHE PATH "ONNX Runtime")
add_library(onnxruntime SHARED IMPORTED)
set_target_properties(onnxruntime PROPERTIES
  IMPORTED_LOCATION "${ORT_ROOT}/lib/libonnxruntime.so.1"
  INTERFACE_INCLUDE_DIRECTORIES "${ORT_ROOT}/include")

# Erkennungskern (ohne Kamera, ohne Dateizugriffe auf Nutzerdaten)
add_library(winky_core STATIC
  src/core/onnx_session.cc
  src/core/face_detection.cc
  src/core/face_embedding.cc
  src/core/face_quality.cc
  src/core/hand_gesture.cc
)
target_include_directories(winky_core PUBLIC src/core)
target_link_libraries(winky_core PUBLIC onnxruntime)
target_compile_options(winky_core PRIVATE -D_GLIBCXX_ASSERTIONS)

add_library(winky_capture STATIC src/capture/v4l2_ir.cc)
target_include_directories(winky_capture PUBLIC src/capture src/core)

# Prüflogik des Dienstes (ohne Kamera und Modelle, testbar)
add_library(winky_dienst STATIC
  src/daemon/konfig.cc
  src/daemon/vorlagen.cc
  src/daemon/entscheidung.cc
  src/daemon/sperre.cc
  src/daemon/sitzung.cc
  src/daemon/anfrage.cc
)
target_include_directories(winky_dienst PUBLIC src/daemon src/protokoll)
target_link_libraries(winky_dienst PUBLIC PkgConfig::SYSTEMD)

# Prüfdienst
add_executable(winky-matcher src/daemon/main.cc)
target_link_libraries(winky-matcher PRIVATE winky_dienst winky_core winky_capture pthread)
set_target_properties(winky-matcher PROPERTIES INSTALL_RPATH "/usr/lib/winky"
                                                 BUILD_RPATH "${ORT_ROOT}/lib")

# PAM-Modul: nur libc und libpam
add_library(pam_winky MODULE src/pam/pam_winky.c)
target_include_directories(pam_winky PRIVATE src/protokoll)
target_link_libraries(pam_winky PRIVATE pam)
set_target_properties(pam_winky PROPERTIES PREFIX "" C_VISIBILITY_PRESET hidden)

# Prüfprogramm für die Polkit-Regel (KeePassXC): nur libc
add_executable(winky-polkit-pruefung src/polkit/winky_polkit_pruefung.c)
target_include_directories(winky-polkit-pruefung PRIVATE src/protokoll)

# Messwerkzeug für die Entwicklung (nicht im Paket)
add_executable(winky-messung werkzeuge/messung/main.cc)
target_link_libraries(winky-messung PRIVATE winky_core winky_capture pthread)
set_target_properties(winky-messung PROPERTIES INSTALL_RPATH "/usr/lib/winky"
                                                 BUILD_RPATH "$ORIGIN;${ORT_ROOT}/lib")

enable_testing()
add_executable(test_dienst tests/test_dienst.cc)
target_link_libraries(test_dienst PRIVATE winky_dienst)
target_compile_options(test_dienst PRIVATE -Wno-unused-result)
add_test(NAME dienst COMMAND test_dienst)

install(TARGETS winky-matcher winky-polkit-pruefung RUNTIME DESTINATION libexec/winky)
install(TARGETS pam_winky LIBRARY DESTINATION lib/x86_64-linux-gnu/security)

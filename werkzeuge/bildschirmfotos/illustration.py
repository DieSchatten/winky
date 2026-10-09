"""Gezeichnetes IR-Kamerabild für die Bildschirmfotos: eine Schaufensterpuppe
statt eines echten Gesichts. Ausgabe: Rohdaten RGB mit Kopfzeile "<b> <h>\\n"."""

import math
import sys

import cairo

B, H = 640, 360


def zeichne():
    s = cairo.ImageSurface(cairo.FORMAT_RGB24, B, H)
    cr = cairo.Context(s)

    def grau(v):
        return (v / 255, v / 255, v / 255)

    # Hintergrund: dunkler Raum, zur Mitte hin vom IR-Strahler aufgehellt
    g = cairo.RadialGradient(B / 2, H / 2, 40, B / 2, H / 2, 420)
    g.add_color_stop_rgb(0, *grau(58))
    g.add_color_stop_rgb(1, *grau(14))
    cr.set_source(g)
    cr.paint()

    # Schultern und Hals
    cr.move_to(150, H)
    cr.curve_to(170, 300, 230, 282, 290, 276)
    cr.line_to(350, 276)
    cr.curve_to(410, 282, 470, 300, 490, H)
    cr.close_path()
    g = cairo.LinearGradient(0, 270, 0, H)
    g.add_color_stop_rgb(0, *grau(96))
    g.add_color_stop_rgb(1, *grau(60))
    cr.set_source(g)
    cr.fill()
    cr.rectangle(290, 230, 60, 52)
    cr.set_source_rgb(*grau(120))
    cr.fill()

    # Kopf: Haut erscheint im Infrarot hell
    cr.save()
    cr.translate(320, 158)
    cr.scale(68, 90)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()
    g = cairo.RadialGradient(305, 140, 10, 320, 160, 105)
    g.add_color_stop_rgb(0, *grau(222))
    g.add_color_stop_rgb(0.7, *grau(176))
    g.add_color_stop_rgb(1, *grau(110))
    cr.set_source(g)
    cr.fill()

    # Haare erscheinen dunkel
    cr.move_to(252, 150)
    cr.curve_to(244, 80, 292, 62, 322, 64)
    cr.curve_to(356, 64, 398, 84, 389, 150)
    cr.curve_to(380, 112, 350, 98, 320, 100)
    cr.curve_to(290, 100, 262, 112, 252, 150)
    cr.close_path()
    cr.set_source_rgb(*grau(80))
    cr.fill()

    # Angedeutete Augen, Nase, Mund
    for x in (294, 346):
        cr.save()
        cr.translate(x, 152)
        cr.scale(13, 6)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.set_source_rgb(*grau(120))
        cr.fill()
    cr.move_to(320, 160)
    cr.curve_to(316, 178, 312, 186, 320, 190)
    cr.set_source_rgb(*grau(150))
    cr.set_line_width(3)
    cr.stroke()
    cr.move_to(300, 212)
    cr.curve_to(312, 220, 328, 220, 340, 212)
    cr.set_source_rgb(*grau(128))
    cr.set_line_width(4)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.stroke()

    # Gesichtsrahmen wie in der App (grün = Gesicht brauchbar)
    cr.rectangle(246, 62, 148, 196)
    cr.set_source_rgb(60 / 255, 220 / 255, 90 / 255)
    cr.set_line_width(3)
    cr.stroke()

    s.flush()
    roh = bytes(s.get_data())
    rgb = bytearray(B * H * 3)
    stride = s.get_stride()
    for y in range(H):
        zeile = roh[y * stride:y * stride + B * 4]
        rgb[y * B * 3:(y + 1) * B * 3 - 2:3] = zeile[2::4]
        rgb[y * B * 3 + 1:(y + 1) * B * 3 - 1:3] = zeile[1::4]
        rgb[y * B * 3 + 2:(y + 1) * B * 3:3] = zeile[0::4]
    return s, bytes(rgb)


if __name__ == "__main__":
    flaeche, rgb = zeichne()
    if sys.argv[1].endswith(".png"):
        flaeche.write_to_png(sys.argv[1])
    else:
        with open(sys.argv[1], "wb") as f:
            f.write(f"{B} {H}\n".encode() + rgb)

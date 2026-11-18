"""
make_ico.py - genera NullPrn.ico a partir del mismo diseño de impresora del tray.
Dibuja el icono "activo" (verde) en alta resolucion y lo empaqueta en un .ico
multi-tamano para el ejecutable y accesos directos de Windows.

Uso:  python make_ico.py
"""
from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]


def make_icon(size, on=True):
    """Version escalable del diseno del tray (coordenadas base 64x64)."""
    s = size / 64.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (40, 170, 80) if on else (150, 150, 150)

    def box(x0, y0, x1, y1, fill):
        d.rectangle((x0 * s, y0 * s, x1 * s, y1 * s), fill=fill)

    box(10, 22, 54, 46, color)            # cuerpo
    box(18, 8, 46, 22, (230, 230, 230))   # papel superior
    box(18, 46, 46, 58, (230, 230, 230))  # papel inferior
    return img


def main():
    base = make_icon(256, on=True)
    frames = [make_icon(sz, on=True) for sz in SIZES]
    base.save("NullPrn.ico", format="ICO",
              sizes=[(f.width, f.height) for f in frames])
    print(f"NullPrn.ico generado con tamanos: {SIZES}")


if __name__ == "__main__":
    main()

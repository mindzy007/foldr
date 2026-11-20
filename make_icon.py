import io
import struct
import sys

from PIL import Image, ImageDraw


def small_icon(size):
    render_size = size * 4
    scale = render_size / 64
    image = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))

    def coords(values):
        return tuple(round(value * scale) for value in values)

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        coords((1, 1, 63, 63)),
        radius=round(12 * scale),
        fill="#FFFFFF",
        outline="#C8EFFF",
        width=max(1, round(scale)),
    )

    folder_points = (
        (7, 21),
        (9, 15),
        (12, 13),
        (27, 13),
        (33, 19),
        (53, 19),
        (57, 23),
        (57, 48),
        (54, 52),
        (10, 52),
        (6, 48),
        (6, 24),
    )
    polygon = [coords(point) for point in folder_points]
    draw.polygon(polygon, fill="#087FB7", outline="#005C87", width=max(1, round(2 * scale)))

    face_box = coords((8, 25, 56, 50))
    face_mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(face_mask).rounded_rectangle(
        face_box, radius=round(4 * scale), fill=255
    )
    gradient = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    top = (41, 195, 247)
    bottom = (0, 145, 216)
    for y in range(face_box[1], face_box[3] + 1):
        amount = (y - face_box[1]) / max(1, face_box[3] - face_box[1])
        color = tuple(round(top[i] + (bottom[i] - top[i]) * amount) for i in range(3))
        gradient_draw.line((face_box[0], y, face_box[2], y), fill=(*color, 255))
    image.alpha_composite(Image.composite(gradient, Image.new("RGBA", image.size), face_mask))

    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        face_box,
        radius=round(4 * scale),
        outline="#0077B5",
        width=max(1, round(scale)),
    )
    draw.line(
        (face_box[0] + round(3 * scale), face_box[1] + round(scale),
         face_box[2] - round(3 * scale), face_box[1] + round(scale)),
        fill="#B8EEFF",
        width=max(1, round(scale)),
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main(source_path, output_path):
    with Image.open(source_path) as source:
        source = source.convert("RGBA")
        sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
        images = []
        for size in sizes:  # every size now comes from your icon.png
            images.append(source.resize((size, size), Image.Resampling.LANCZOS))

    png_frames = []
    for image in images:
        stream = io.BytesIO()
        image.save(stream, format="PNG", optimize=True)
        png_frames.append(stream.getvalue())

    directory_size = 6 + 16 * len(sizes)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = []
    offset = directory_size
    for size, data in zip(sizes, png_frames):
        dimension = 0 if size == 256 else size
        entries.append(struct.pack(
            "<BBBBHHII",
            dimension,
            dimension,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        ))
        offset += len(data)

    with open(output_path, "wb") as icon_file:
        icon_file.write(header)
        icon_file.writelines(entries)
        icon_file.writelines(png_frames)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

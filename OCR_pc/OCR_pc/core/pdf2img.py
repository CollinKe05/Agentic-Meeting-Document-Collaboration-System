import fitz  # PyMuPDF
import os

def pdf_to_images(pdf_path, output_dir="pages", zoom=2):

    os.makedirs(output_dir, exist_ok=True)

    doc = fitz.open(pdf_path)

    image_paths = []

    for page_index in range(len(doc)):

        page = doc[page_index]

        mat = fitz.Matrix(zoom, zoom)

        pix = page.get_pixmap(matrix=mat)

        img_path = f"{output_dir}/page_{page_index}.png"

        pix.save(img_path)

        image_paths.append(img_path)

    return image_paths
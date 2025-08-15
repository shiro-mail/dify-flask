from PIL import Image
import os

os.makedirs('test_images', exist_ok=True)

colors = [
    (255, 0, 0),    # Red
    (0, 255, 0),    # Green  
    (0, 0, 255)     # Blue
]

for i, color in enumerate(colors, 1):
    img = Image.new('RGB', (100, 100), color)
    img.save(f'test_images/test_image_{i}.png')
    print(f'Created test_images/test_image_{i}.png')

print("Test images created successfully!")

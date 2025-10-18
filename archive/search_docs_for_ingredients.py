"""
Поиск информации об ингредиентах в PDF документации
"""

import PyPDF2
import os
import re

docs_folder = "Документация"

# Ключевые слова для поиска
keywords = [
    "ингредиент",
    "ingredient",
    "расход",
    "consumption",
    "кега",
    "кег",
    "keg",
    "DishIngredient",
    "ProductIngredient",
    "IngredientName",
    "Amount",
    "расходования",
    "списани"
]

print("="*80)
print("POISK INFORMACII OB INGREDIENTAKH V DOKUMENTACII")
print("="*80)

# Файлы для изучения
pdf_files = [
    "primery-vyzova-olap-otchet-v2.pdf",
    "prednastroennye-olap-otchety-vv2.pdf",
    "sobytiya.pdf",
    "olap-otchety-v2.pdf"
]

results = {}

for pdf_file in pdf_files:
    filepath = os.path.join(docs_folder, pdf_file)

    if not os.path.exists(filepath):
        continue

    print(f"\n{'='*80}")
    print(f"Izuchayu: {pdf_file}")
    print("="*80)

    try:
        with open(filepath, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)

            found_pages = []

            for page_num in range(min(len(pdf_reader.pages), 50)):  # Первые 50 страниц
                page = pdf_reader.pages[page_num]
                text = page.extract_text().lower()

                # Ищем ключевые слова
                for keyword in keywords:
                    if keyword.lower() in text:
                        found_pages.append((page_num + 1, keyword))
                        break

            if found_pages:
                print(f"\n[FOUND] Nayden upominaniya na stranicakh:")
                for page_num, keyword in found_pages[:10]:  # Первые 10 совпадений
                    print(f"  Stranica {page_num}: {keyword}")

                results[pdf_file] = found_pages
            else:
                print(f"[NOT FOUND] Klyuchevye slova ne naydeny")

    except Exception as e:
        print(f"[ERROR] {e}")

print("\n" + "="*80)
print("ITOGO:")
print("="*80)

if results:
    print(f"\nNayden informaciya v {len(results)} faylakh:")
    for filename, pages in results.items():
        print(f"\n{filename}:")
        print(f"  Stranici: {', '.join([str(p[0]) for p in pages[:10]])}")
else:
    print("\nInformaciya ob ingredientakh ne naydena v PDF")
    print("Vozmozhno, nuzhno ispolzovat drugoy podkhod")

print("\n" + "="*80)
print("REKOMENDACII:")
print("="*80)
print("""
1. Proverit stranici gde nayden upominaniya
2. Vozmozhnye варианты:
   - SALES otchet s agregaciei po ingredientam
   - Otdelnyy endpoint dlya raskhoda produktov
   - STOCK otchet s filtrami po tipu sobytiy
   - Prednastroennyy otchet iz iiko Office
""")

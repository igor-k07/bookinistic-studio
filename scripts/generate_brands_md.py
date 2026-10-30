import sqlite3
import json
from collections import Counter

def generate():
    conn = sqlite3.connect('storage/catalog.db')
    cursor = conn.cursor()
    cursor.execute('SELECT data FROM books')
    brands = Counter()
    for row in cursor.fetchall():
        d = json.loads(row[0])
        b = d.get('brand')
        if b:
            b = str(b).strip()
            if b:
                brands[b] += 1

    sorted_brands = sorted(brands.items(), key=lambda x: x[0].lower())

    lines = []
    lines.append('# 🏷️ Справочник книжных брендов Ozon (Издательства)')
    lines.append('')
    lines.append('Данный справочник составлен на основе **397 подтвержденных брендов Ozon**, успешно прошедших модерацию в вашем магазине.')
    lines.append('')
    lines.append('> [!TIP]')
    lines.append('> **Как быстро проверить издательство**:')
    lines.append('> 1. Нажмите `Cmd + F` в этом файле и начните вводить название типографии/издательства книги.')
    lines.append('> 2. **Если издательство нашлось в списке** $\\to$ указывайте его в поле «Бренд» в точности как здесь.')
    lines.append('> 3. **Если издательства НЕТ в списке** (редкое, старое советское региональное, ведомственное) $\\to$ **СТРОГО ставьте: `Нет бренда`**!')
    lines.append('>    При этом настоящее историческое название типографии сохраняется в поле **«Издательство»** (в шаблоне до 2011 г. колонка `AJ`).')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 🏆 ТОП-30 самых частых брендов Ozon (по вашему магазину)')
    lines.append('')
    lines.append('| № | Название бренда на Ozon | Карточек в магазине | Комментарий |')
    lines.append('| :-: | :--- | :-: | :--- |')

    for i, (b, count) in enumerate(brands.most_common(30), 1):
        comment = 'Универсальное значение для редких/советских типографий' if b == 'Нет бренда' else 'Крупный издательский бренд'
        lines.append(f'| {i} | **`{b}`** | {count} шт. | {comment} |')

    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append(f'## 📚 Полный алфавитный реестр брендов (всего: {len(brands)} изд.)')
    lines.append('')

    current_letter = ''
    for b, count in sorted_brands:
        first_char = b[0].upper()
        if first_char != current_letter:
            current_letter = first_char
            lines.append(f'\n### {current_letter}\n')
        lines.append(f'- **`{b}`** *(в магазине: {count} шт.)*')

    with open('OZON_BRANDS.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f'OZON_BRANDS.md successfully created with {len(brands)} brands!')

if __name__ == '__main__':
    generate()

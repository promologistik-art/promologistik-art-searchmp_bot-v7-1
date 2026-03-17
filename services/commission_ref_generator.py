# services/commission_ref_generator.py
import pandas as pd
import io
import re
from fuzzywuzzy import fuzz, process
from datetime import datetime
import os
from typing import List, Dict, Tuple, Optional


class CommissionRefGenerator:
    """
    Генератор справочника комиссий.
    Сопоставляет категории из template_categories.xlsx с типами товаров из catcom.xlsx
    и создает единый файл-справочник.
    """

    PRICE_COLUMNS = [
        'до 100 руб.',
        'свыше 100 <br>до 300 руб.',
        'свыше 300 <br>до 1500 руб.',
        'свыше 1500 <br>до 5000 руб.',
        'свыше 5000 <br>до 10 000 руб.',
        'свыше <br>10 000 руб.'
    ]

    def __init__(self):
        self.results = []

    def _normalize_string(self, s: str) -> str:
        """Приводит строку к нормальному виду для поиска"""
        if not isinstance(s, str):
            return ""
        s = s.lower().strip()
        s = re.sub(r'\s+', ' ', s)
        s = re.sub(r'[^\w\s]', '', s)
        return s

    def _extract_keywords(self, text: str) -> List[str]:
        """Извлекает ключевые слова (слова длиннее 3 символов)"""
        if not text:
            return []
        words = self._normalize_string(text).split()
        return [w for w in words if len(w) > 3]

    def _find_best_match(
        self,
        category_name: str,
        full_path: str,
        catcom_df: pd.DataFrame
    ) -> Tuple[Optional[pd.Series], str]:
        """
        Ищет лучшее соответствие для категории в catcom.
        Возвращает (строка из catcom, статус)
        Статусы: 'ТОЧНОЕ СОВПАДЕНИЕ', 'ПО КЛЮЧЕВЫМ СЛОВАМ', 'НЕ НАЙДЕНО'
        """
        print(f"\n  🔍 Ищем для: '{category_name}'")
        print(f"  📂 Полный путь: '{full_path}'")

        norm_name = self._normalize_string(category_name)
        norm_path = self._normalize_string(full_path)

        # УРОВЕНЬ 1: Точное совпадение по названию
        print("  Уровень 1: Точное совпадение по названию...")
        for idx, row in catcom_df.iterrows():
            prod_type = str(row['Тип товара']) if pd.notna(row['Тип товара']) else ''
            if self._normalize_string(prod_type) == norm_name:
                print(f"  ✅ ТОЧНОЕ СОВПАДЕНИЕ: '{prod_type}'")
                return row, 'ТОЧНОЕ СОВПАДЕНИЕ'

        # УРОВЕНЬ 2: Поиск по ключевым словам
        print("  Уровень 2: Поиск по ключевым словам...")
        keywords = self._extract_keywords(category_name)
        if not keywords:
            keywords = self._extract_keywords(full_path)

        if keywords:
            print(f"  Ключевые слова: {keywords}")
            keyword_matches = []
            for idx, row in catcom_df.iterrows():
                prod_type = str(row['Тип товара']) if pd.notna(row['Тип товара']) else ''
                if not prod_type:
                    continue
                norm_prod = self._normalize_string(prod_type)
                match_count = sum(1 for kw in keywords if kw in norm_prod)
                if match_count > 0:
                    keyword_matches.append((match_count, idx, row, prod_type))

            if keyword_matches:
                keyword_matches.sort(reverse=True)
                best_count, best_idx, best_row, best_type = keyword_matches[0]
                print(f"  ✅ ПО КЛЮЧЕВЫМ СЛОВАМ: '{best_type}' (совпадений: {best_count})")
                return best_row, 'ПО КЛЮЧЕВЫМ СЛОВАМ'

        # УРОВЕНЬ 3: Нечеткое сравнение
        print("  Уровень 3: Нечеткое сравнение...")
        catcom_types = catcom_df['Тип товара'].dropna().tolist()
        best_match, score = process.extractOne(
            norm_name,
            catcom_types,
            scorer=fuzz.token_sort_ratio
        )

        if score >= 60:  # Порог сходства
            print(f"  ✅ НЕЧЕТКОЕ СОВПАДЕНИЕ: '{best_match}' (сходство {score}%)")
            row = catcom_df[catcom_df['Тип товара'] == best_match].iloc[0]
            return row, f'НЕЧЕТКОЕ СОВПАДЕНИЕ ({score}%)'

        print("  ❌ НЕ НАЙДЕНО")
        return None, 'НЕ НАЙДЕНО'

    def generate(self, template_path: str, catcom_path: str) -> io.BytesIO:
        """
        Генерирует справочник комиссий.

        Args:
            template_path: путь к файлу template_categories.xlsx
            catcom_path: путь к файлу catcom.xlsx

        Returns:
            BytesIO объект с Excel файлом
        """
        print("📂 Загружаем файлы...")

        # Загружаем шаблон категорий
        template_df = pd.read_excel(template_path, sheet_name='Категории')
        print(f"   ✓ Категорий в шаблоне: {len(template_df)}")

        # Загружаем файл с комиссиями (пропускаем первую строку с заголовком "FBO")
        catcom_df = pd.read_excel(catcom_path, sheet_name='Прайс (БЗ)', header=1)
        print(f"   ✓ Строк в catcom: {len(catcom_df)}")

        results = []
        stats = {
            'ТОЧНОЕ СОВПАДЕНИЕ': 0,
            'ПО КЛЮЧЕВЫМ СЛОВАМ': 0,
            'НЕЧЕТКОЕ СОВПАДЕНИЕ': 0,
            'НЕ НАЙДЕНО': 0
        }

        print("\n🔄 Обрабатываем категории...")

        for idx, row in template_df.iterrows():
            if idx % 100 == 0 and idx > 0:
                print(f"   Обработано {idx}/{len(template_df)}...")
                print(f"      Статистика: {stats}")

            category_name = row['Категория']
            main_category = row['Основная категория']
            subcategory = row['Подкатегория']
            full_path = row['Полный путь']

            # Ищем соответствие
            match_row, status = self._find_best_match(category_name, full_path, catcom_df)

            # Формируем результат
            result_row = {
                '№': idx + 1,
                'Категория': category_name,
                'Основная категория': main_category,
                'Подкатегория': subcategory,
                'Полный путь': full_path,
                'Статус': status,
                'Категория в catcom': '',
                'Тип товара в catcom': '',
            }

            # Добавляем колонки с комиссиями
            for col in self.PRICE_COLUMNS:
                result_row[col] = None

            if match_row is not None:
                # Обновляем статистику
                main_status = status.split(' (')[0]  # отрезаем процент для нечеткого совпадения
                stats[main_status] = stats.get(main_status, 0) + 1

                result_row['Категория в catcom'] = match_row['Категория']
                result_row['Тип товара в catcom'] = match_row['Тип товара']

                # Копируем комиссии
                for col in self.PRICE_COLUMNS:
                    if col in match_row:
                        result_row[col] = match_row[col]
            else:
                stats['НЕ НАЙДЕНО'] += 1

            results.append(result_row)

        # Создаем DataFrame
        result_df = pd.DataFrame(results)

        # Сохраняем в BytesIO
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            result_df.to_excel(writer, index=False, sheet_name='Справочник комиссий')

            # Добавляем лист со статистикой
            stats_df = pd.DataFrame([
                {'Тип совпадения': k, 'Количество': v, 'Процент': f'{v/len(results)*100:.1f}%'}
                for k, v in stats.items()
            ])
            stats_df.to_excel(writer, sheet_name='Статистика', index=False)

        output.seek(0)

        print(f"\n✅ Готово! Статистика:")
        for k, v in stats.items():
            print(f"   {k}: {v} ({v/len(results)*100:.1f}%)")

        return output

"""
Тест нечеткого сравнения названий
"""

# Название из крана (после удаления "КЕГ")
tap_name = "Ригеле Альте Вайс"

# Название из номенклатуры (после обработки)
keg_name = "Ригеле Альт Вайс С"

print("=" * 60)
print("ТЕСТ НЕЧЕТКОГО СРАВНЕНИЯ")
print("=" * 60)

print(f"\nНазвание на кране: '{tap_name}'")
print(f"Название кеги: '{keg_name}'")

# Нормализация
tap_norm = tap_name.lower().strip()
keg_norm = keg_name.lower().strip()

print(f"\nПосле lower():")
print(f"  Кран: '{tap_norm}'")
print(f"  Кега: '{keg_norm}'")

# Проверка вхождения
tap_in_keg = tap_norm in keg_norm
keg_in_tap = keg_norm in tap_norm

print(f"\nПроверка вхождения:")
print(f"  tap in keg: {tap_in_keg}")
print(f"  keg in tap: {keg_in_tap}")

if tap_in_keg or keg_in_tap:
    print("\n✓ СОВПАДЕНИЕ по нечеткому сравнению!")
else:
    print("\n✗ НЕТ СОВПАДЕНИЯ")

    # Попробуем понять почему
    print("\nАнализ различий:")
    print(f"  Длина tap: {len(tap_norm)}, keg: {len(keg_norm)}")

    # Посимвольное сравнение
    print("\n  Посимвольно:")
    max_len = max(len(tap_norm), len(keg_norm))
    for i in range(max_len):
        tap_char = tap_norm[i] if i < len(tap_norm) else ' '
        keg_char = keg_norm[i] if i < len(keg_norm) else ' '

        if tap_char != keg_char:
            print(f"    Позиция {i}: '{tap_char}' != '{keg_char}'")

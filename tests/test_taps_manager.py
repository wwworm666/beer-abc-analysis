"""
Тест чтения taps_manager
"""
import sys
sys.path.insert(0, 'c:\\KULT\\beer-abc-analysis')

from core.taps_manager import TapsManager

taps_manager = TapsManager(data_file='data/taps_data.json')

print("=" * 60)
print("ТЕСТ TAPS MANAGER")
print("=" * 60)

for bar_id in ['bar1', 'bar2', 'bar3', 'bar4']:
    result = taps_manager.get_bar_taps(bar_id)
    print(f"\n{bar_id}: {result.get('name', 'N/A')}")
    print(f"  Taps count: {len(result.get('taps', []))}")

    if 'taps' in result:
        active_count = 0
        for tap in result['taps']:
            if tap.get('status') == 'active':
                active_count += 1
                print(f"  Active tap {tap.get('tap_number')}: {tap.get('current_beer')}")

        print(f"  Total active: {active_count}")

print(f"\n{'=' * 60}")

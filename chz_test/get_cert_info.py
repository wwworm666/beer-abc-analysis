import subprocess
import re

result = subprocess.run(
    [r"C:\Program Files\Crypto Pro\CSP\certmgr.exe", "-list", "-all"],
    capture_output=True,
    text=True,
    encoding='cp866',
    timeout=30
)

output = result.stdout
print(output)

# Сохраняем в файл для анализа
with open(r"C:\Users\1\Desktop\debug\cert_list.txt", "w", encoding="utf-8") as f:
    f.write(output)

print("\n\n[OK] Saved to C:\\Users\\1\\Desktop\\debug\\cert_list.txt")

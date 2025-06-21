Kali Mirror GUI Updater

Этот проект — графический интерфейс для автоматического выбора лучшего зеркала Kali Linux, обновления системы и очистки пакетов.

📌 Описание
Скрипт:

Проверяет доступность нескольких официальных зеркал Kali.
Выбирает самое быстрое.
Обновляет систему.
Исправляет зависимости.
Выполняет очистку системы (autoremove, autoclean, clean).
Всё это — через простой и удобный GUI.

▶️ Как запускать

1. Через Python (с виртуальным окружением)

cd ~/kali-mirror-gui
export DISPLAY=:0
sudo -E python kali_mirror_gui.py

⚠️ Требуется предварительно создать и активировать виртуальное окружение с зависимостями(только в первый раз): 

python3 -m venv venv
source venv/bin/activate
pip install tk subprocess32

2. Как автономный бинарник (без Python)

собрать бинарник

cd ~/kali-mirror-gui
source venv/bin/activate
pyinstaller --onefile --windowed kali_mirror_gui.py

Собранный файл находится в:

~/kali-mirror-gui/dist/kali_mirror_gui

Запустить:

cd ~/kali-mirror-gui/dist
./kali_mirror_gui

🔐 Для выполнения команд с sudo необходимо запускать скрипт от root: 
sudo ./kali_mirror_gui

💡 Функции GUI

Кнопка "Начать проверку зеркал" — запускает процесс выбора лучшего зеркала.

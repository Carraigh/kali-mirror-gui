#!/bin/bash
set -e

echo "[+] Установка python3-tk (обязательно для GUI)..."
sudo apt install -y python3-tk

echo "[+] Установка Python-пакетов в ./lib..."
python3 -m pip install --target ./lib --upgrade requests sv-ttk

echo "[+] Готово! Запускай: sudo python3 kali_mirror_gui.py"

#!/usr/bin/env python3
import sys
import os

# Добавляем ./lib в путь поиска модулей
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

import subprocess
import threading
import time
import shutil
import logging
import requests

# === Настройки ===
LOG_FILE = "/var/log/kali-mirror-gui.log"
USER_MIRRORS_FILE = os.path.expanduser("~/.config/kali-mirror-gui/mirrors.txt")
DEFAULT_MIRRORS = [
    "https://http.kali.org/kali",
    "http://ftp.halifax.rwth-aachen.de/kali",
    "http://kali.mirror.garr.it/mirrors/kali",
    "http://mirror.csclub.uwaterloo.ca/kali",
    "http://kali.download/kali"
]

# === Логирование ===
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(USER_MIRRORS_FILE), exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8"
)

class MirrorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kali Mirror Updater ✨")
        self.root.geometry("600x500")
        self.root.resizable(True, True)

        if os.geteuid() != 0:
            messagebox.showerror("Ошибка", "Запустите с sudo!")
            sys.exit(1)

        # Проверяем, что мы в Kali
        if not self.is_kali():
            self.log("[!] Это не Kali Linux — продолжаем с осторожностью.")

        self.process_running = False
        self.cancel_event = threading.Event()
        self.current_process = None

        # UI
        self.text_box = tk.Text(self.root, wrap="word", height=22, width=80, state='disabled', font=("Monospace", 9))
        self.text_box.pack(pady=10, padx=10)

        self.btn_frame = tk.Frame(self.root)
        self.btn_frame.pack(pady=5)

        self.run_button = ttk.Button(self.btn_frame, text="🔍 Найти лучшее зеркало", command=self.start_process)
        self.run_button.pack(side="left", padx=5)

        self.add_mirror_btn = ttk.Button(self.btn_frame, text="➕ Добавить зеркало", command=self.add_custom_mirror)
        self.add_mirror_btn.pack(side="left", padx=5)

        self.cancel_button = ttk.Button(self.btn_frame, text="❌ Отмена", command=self.cancel_process, state='disabled')
        self.cancel_button.pack(side="left", padx=5)

        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=560, mode="indeterminate")
        self.progress.pack(pady=5)

        # Тема
        try:
            import sv_ttk
            sv_ttk.set_theme("dark")
        except Exception as e:
            self.log(f"[!] Не удалось загрузить sv_ttk: {e}")

    def log(self, msg):
        print(msg)  # Выводим в консоль тоже
        if GUI_AVAILABLE:
            self.text_box.config(state='normal')
            self.text_box.insert(tk.END, msg + "\n")
            self.text_box.config(state='disabled')
            self.text_box.see(tk.END)
        logging.info(msg)

    def is_kali(self):
        try:
            with open("/etc/os-release") as f:
                return "kali" in f.read().lower()
        except:
            return False

    def load_mirrors(self):
        mirrors = DEFAULT_MIRRORS.copy()
        if os.path.exists(USER_MIRRORS_FILE):
            with open(USER_MIRRORS_FILE) as f:
                for line in f:
                    url = line.strip()
                    if url and url not in mirrors:
                        mirrors.append(url)
        return mirrors

    def save_custom_mirror(self, url):
        if not url.startswith(("http://", "https://")):
            return False
        with open(USER_MIRRORS_FILE, "a") as f:
            f.write(url + "\n")
        return True

    def add_custom_mirror(self):
        if not GUI_AVAILABLE:
            url = input("Введите URL зеркала (например, https://mirror.example.com/kali): ")
            if self.save_custom_mirror(url):
                self.log(f"[+] Добавлено пользовательское зеркало: {url}")
            else:
                print("Некорректный URL.")
            return
        url = simpledialog.askstring("Новое зеркало", "Введите URL зеркала (например, https://mirror.example.com/kali):")
        if url:
            if self.save_custom_mirror(url):
                self.log(f"[+] Добавлено пользовательское зеркало: {url}")
            else:
                messagebox.showerror("Ошибка", "Некорректный URL.")

    def has_internet(self):
        try:
            requests.get("https://1.1.1.1", timeout=3)
            return True
        except:
            return False

    def start_process(self):
        if self.process_running:
            return
        if not self.has_internet():
            if GUI_AVAILABLE:
                messagebox.showerror("Нет интернета", "Проверьте подключение к интернету.")
            else:
                print("Нет интернета — проверьте подключение.")
            return
        self.cancel_event.clear()
        self.run_button.config(state='disabled')
        self.add_mirror_btn.config(state='disabled')
        self.cancel_button.config(state='normal')
        self.progress.start()
        self.process_running = True
        self.log("[+] Запуск процесса...")
        threading.Thread(target=self.full_update_process, daemon=True).start()

    def cancel_process(self):
        self.log("[!] Отмена...")
        self.cancel_event.set()
        if self.current_process:
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=3)
            except:
                pass

    def full_update_process(self):
        try:
            mirrors = self.load_mirrors()
            self.log(f"[+] Проверка {len(mirrors)} зеркал...")

            best = self.find_best_mirror(mirrors)
            if not best:
                raise Exception("Ни одно зеркало не отвечает.")

            self.log(f"[+] Выбрано: {best}")
            self.set_sources_list(best)
            if self.cancel_event.is_set(): return

            self.run_cmd("apt-get update -y")
            if self.cancel_event.is_set(): return

            self.run_cmd("apt-get upgrade -y")
            if self.cancel_event.is_set(): return

            self.run_cmd("apt-get install -f -y")
            if self.cancel_event.is_set(): return

            self.run_cmd("apt-get autoremove -y")
            self.run_cmd("apt-get autoclean -y")
            self.run_cmd("apt-get clean -y")

            self.log("[✅] Готово!")
            if GUI_AVAILABLE:
                messagebox.showinfo("Успех", "Система обновлена и очищена!")
            else:
                print("✅ Система обновлена и очищена!")
        except Exception as e:
            err = str(e)
            self.log(f"[!] Ошибка: {err}")
            if GUI_AVAILABLE:
                messagebox.showerror("Ошибка", err)
            else:
                print(f"❌ Ошибка: {err}")
        finally:
            if GUI_AVAILABLE:
                self.progress.stop()
                self.process_running = False
                self.run_button.config(state='normal')
                self.add_mirror_btn.config(state='normal')
                self.cancel_button.config(state='disabled')

    def find_best_mirror(self, mirrors):
        results = []
        for mirror in mirrors:
            if self.cancel_event.is_set():
                return None
            url = f"{mirror.rstrip('/')}/dists/kali-rolling/InRelease"
            try:
                self.log(f"[-] Тестирую {mirror}...")
                start = time.time()
                resp = requests.head(url, timeout=8)
                if resp.status_code == 200:
                    latency = time.time() - start
                    results.append((latency, mirror))
                    self.log(f"    ✅ {latency:.2f}s")
                else:
                    self.log(f"    ❌ HTTP {resp.status_code}")
            except Exception as e:
                self.log(f"    ❌ Ошибка: {e}")
        if not results:
            return None
        results.sort(key=lambda x: x[0])
        return results[0][1]

    def set_sources_list(self, mirror):
        bak = "/etc/apt/sources.list.bak"
        if not os.path.exists(bak):
            shutil.copy2("/etc/apt/sources.list", bak)
            self.log(f"[+] Создан бэкап: {bak}")

        content = f"deb {mirror} kali-rolling main contrib non-free non-free-firmware\n"
        tmp = "/tmp/sources.list"
        with open(tmp, "w") as f:
            f.write(content)
        shutil.move(tmp, "/etc/apt/sources.list")
        self.log("[OK] sources.list обновлён")

    def run_cmd(self, cmd):
        if self.cancel_event.is_set():
            return
        self.log(f"> {cmd}")
        try:
            proc = subprocess.Popen(
                cmd.split(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            self.current_process = proc
            for line in iter(proc.stdout.readline, ''):
                if self.cancel_event.is_set():
                    proc.terminate()
                    raise Exception("Отменено пользователем")
                if line.strip():
                    self.log("  " + line.rstrip())
            proc.wait()
            if proc.returncode != 0:
                raise Exception(f"Ошибка выполнения: {cmd}")
        finally:
            self.current_process = None

def main():
    if not GUI_AVAILABLE:
        print("⚠️  GUI недоступен — запускаю в режиме командной строки.")
        app = MirrorApp(None)  # Можно передать None, если GUI не нужен
        app.full_update_process()
        return

    root = tk.Tk()
    app = MirrorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

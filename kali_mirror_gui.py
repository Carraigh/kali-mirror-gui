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
            if GUI_AVAILABLE:
                messagebox.showerror("Ошибка", "Запустите с sudo!")
            else:
                print("Ошибка: запустите с sudo!")
            sys.exit(1)

        # Проверяем, что мы в Kali
        if not self.is_kali():
            self.log("[!] Это не Kali Linux — продолжаем с осторожностью.")

        self.process_running = False
        self.cancel_event = threading.Event()
        self.current_process = None

        # UI
        if GUI_AVAILABLE:
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
        print(msg)
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

    def clean_url(self, url):
        """Удаляет пробелы и нормализует URL"""
        return url.strip().rstrip('/')

    def load_mirrors(self):
        mirrors = []
        all_urls = set()

        # DEFAULT_MIRRORS
        for url in DEFAULT_MIRRORS:
            clean = self.clean_url(url)
            if clean and clean not in all_urls:
                mirrors.append(clean)
                all_urls.add(clean)

        # USER_MIRRORS_FILE
        if os.path.exists(USER_MIRRORS_FILE):
            with open(USER_MIRRORS_FILE) as f:
                for line in f:
                    clean = self.clean_url(line)
                    if clean and clean.startswith(("http://", "https://")) and clean not in all_urls:
                        mirrors.append(clean)
                        all_urls.add(clean)
        return mirrors

    def save_custom_mirror(self, url):
        clean = self.clean_url(url)
        if not clean.startswith(("http://", "https://")):
            return False
        with open(USER_MIRRORS_FILE, "a") as f:
            f.write(clean + "\n")
        return True

    def add_custom_mirror(self):
        if not GUI_AVAILABLE:
            url = input("Введите URL зеркала (например, https://mirror.example.com/kali): ")
            if self.save_custom_mirror(url):
                self.log(f"[+] Добавлено пользовательское зеркало: {url}")
            else:
                print("Некорректный URL.")
            return
        url = simpledialog.askstring("Новое зеркало", "Введите URL зеркала:")
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
            msg = "Проверьте подключение к интернету."
            if GUI_AVAILABLE:
                messagebox.showerror("Нет интернета", msg)
            else:
                print("❌ " + msg)
            return
        self.cancel_event.clear()
        if GUI_AVAILABLE:
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

            # Тестируем зеркала по скорости загрузки Packages.gz
            results = []
            for mirror in mirrors:
                if self.cancel_event.is_set():
                    return
                score = self.test_mirror(mirror)
                if score:
                    results.append((score, mirror))
                    self.log(f"    ✅ {mirror} — {score:.2f} байт/с")
                else:
                    self.log(f"    ❌ {mirror} — не отвечает")

            if not results:
                raise Exception("Ни одно зеркало не прошло тест.")

            # Сортируем по скорости (чем выше — тем лучше)
            results.sort(key=lambda x: x[0], reverse=True)
            ranked_mirrors = [mirror for _, mirror in results]

            # Создаём бэкап sources.list один раз
            bak = "/etc/apt/sources.list.bak"
            if not os.path.exists(bak):
                shutil.copy2("/etc/apt/sources.list", bak)
                self.log(f"[+] Создан бэкап: {bak}")

            # Пробуем зеркала по одному, пока не найдём рабочее
            working_mirror = None
            for mirror in ranked_mirrors:
                if self.cancel_event.is_set():
                    return
                self.log(f"[→] Пробую зеркало: {mirror}")
                self.set_sources_list(mirror)
                try:
                    self.run_cmd("apt-get update -y", check_apt_update=True)
                    working_mirror = mirror
                    break
                except Exception as e:
                    self.log(f"[!] Зеркало не подошло: {e}")

            if not working_mirror:
                raise Exception("Ни одно зеркало не работает стабильно.")

            self.log(f"[+] Используем: {working_mirror}")

            # Продолжаем обновление
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

    def test_mirror(self, mirror, timeout=8):
        """
        Тестирует зеркало: пытается загрузить 10 КБ из Packages.gz.
        Возвращает скорость в байтах/сек, или None при ошибке.
        """
        url = f"{mirror.rstrip('/')}/dists/kali-rolling/main/binary-amd64/Packages.gz"
        try:
            start = time.time()
            resp = requests.get(url, timeout=timeout, stream=True, allow_redirects=True)
            if resp.status_code != 200:
                return None
            chunk = next(resp.iter_content(chunk_size=10240), b'')
            if not chunk:
                return None
            elapsed = time.time() - start
            if elapsed <= 0:
                return None
            return len(chunk) / elapsed  # bytes per second
        except Exception:
            return None

    def set_sources_list(self, mirror):
        content = f"deb {mirror} kali-rolling main contrib non-free non-free-firmware\n"
        tmp = "/tmp/sources.list"
        with open(tmp, "w") as f:
            f.write(content)
        shutil.move(tmp, "/etc/apt/sources.list")
        self.log("[OK] sources.list обновлён")

    def run_cmd(self, cmd, check_apt_update=False):
        if self.cancel_event.is_set():
            return
        self.log(f"> {cmd}")
        output_lines = []
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
                line = line.rstrip()
                if line:
                    self.log("  " + line)
                    output_lines.append(line)
            proc.wait()
            # Проверка "мягких" ошибок apt
            if check_apt_update and proc.returncode == 0:
                if any(
                    phrase in line for line in output_lines
                    for phrase in ["Не удалось получить", "Failed to fetch", "время ожидания", "timeout"]
                ):
                    raise Exception("apt-get update завершился с ошибками загрузки")
            if proc.returncode != 0:
                raise Exception(f"Команда завершилась с ошибкой: {cmd}")
        finally:
            self.current_process = None

def main():
    if not GUI_AVAILABLE:
        print("⚠️  GUI недоступен — запускаю в режиме командной строки.")
        app = MirrorApp(None)
        app.full_update_process()
        return

    root = tk.Tk()
    app = MirrorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()

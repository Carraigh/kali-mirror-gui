import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import os
import tempfile
import threading
import sys

# Проверяем, есть ли виртуальное окружение
venv_dir = os.path.join(os.path.dirname(__file__), "venv")
script_dir = os.path.dirname(__file__)

KALI_MIRRORS = [
    "https://http.kali.org/kali", 
    "http://ftp.halifax.rwth-aachen.de/kali",
    "http://kali.mirror.garr.it/mirrors/kali",
    "http://mirror.csclub.uwaterloo.ca/kali",
    "http://kali.download/kali"
]

def install_dependencies():
    """Установка зависимостей в venv"""
    if not os.path.exists(venv_dir):
        print("[INFO] Создаю виртуальное окружение...")
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir])

    pip_path = os.path.join(venv_dir, "bin", "pip") if os.name != "nt" else os.path.join(venv_dir, "Scripts", "pip")
    try:
        # Установка зависимостей
        subprocess.check_call([pip_path, "install", "tk"])
        print("[INFO] Зависимости установлены!")
    except Exception as e:
        print(f"[ERROR] Не удалось установить зависимости: {e}")
        sys.exit(1)

class MirrorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Kali Mirror Updater")
        self.root.geometry("500x400")
        self.root.resizable(True, True)

        self.process_running = False
        self.current_process = None

        # Лог-поле
        self.text_box = tk.Text(self.root, wrap="word", height=18, width=60, state='disabled')
        self.text_box.pack(pady=10)

        # Контроллеры
        self.btn_frame = tk.Frame(self.root)
        self.btn_frame.pack(pady=5)

        self.run_button = ttk.Button(self.btn_frame, text="Начать проверку зеркал", command=self.start_process)
        self.run_button.pack(side="left", padx=5)

        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="indeterminate")
        self.progress.pack(pady=5)

    def log(self, message):
        self.text_box.config(state='normal')
        self.text_box.insert(tk.END, message + "\n")
        self.text_box.config(state='disabled')
        self.text_box.see(tk.END)

    def start_process(self):
        if self.process_running:
            return
        self.run_button.config(state='disabled')
        self.progress.start()
        self.process_running = True
        self.log("[+] Запуск процесса...")
        threading.Thread(target=self.full_update_process).start()

    def full_update_process(self):
        try:
            self.log("[+] Поиск лучшего зеркала...")
            best_mirror = self.find_best_mirror()
            if not best_mirror:
                raise Exception("Не найдено рабочих зеркал.")

            self.log(f"[+] Лучшее зеркало: {best_mirror}")
            self.set_sources_list(best_mirror)

            self.log("[+] Обновление пакетов...")
            self.run_cmd("sudo apt-get update -y")

            self.log("[+] Обновление системы...")
            self.run_cmd("sudo apt-get upgrade -y")

            self.log("[+] Исправление зависимостей (install -f)...")
            self.run_cmd("sudo apt-get install -f -y")

            self.log("[+] Очистка системы...")
            self.run_cmd("sudo apt-get autoremove -y")
            self.run_cmd("sudo apt-get autoclean -y")
            self.run_cmd("sudo apt-get clean -y")

            self.log("[+] Готово!")
            self.show_info("Готово", "Обновление и очистка успешно выполнены.")
        except Exception as e:
            self.log(f"[!] Ошибка: {str(e)}")
            self.show_error("Ошибка", str(e))
        finally:
            self.progress.stop()
            self.process_running = False
            self.run_button.config(state='normal')

    def show_info(self, title, message):
        self.root.after(0, lambda: messagebox.showinfo(title, message))

    def show_error(self, title, message):
        self.root.after(0, lambda: messagebox.showerror(title, message))

    def find_best_mirror(self):
        tmp_ping = tempfile.mktemp()
        with open(tmp_ping, 'w') as f:
            pass

        for mirror in KALI_MIRRORS:
            host = mirror.split("//")[1].split("/")[0]
            self.log(f"[-] Проверяю {host}...")

            ping_test = subprocess.run(["ping", "-c", "2", host], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ping_test.returncode != 0:
                continue

            ping_result = subprocess.run(["ping", "-c", "5", host], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            avg_ping = self.parse_ping_output(ping_result.stdout)
            with open(tmp_ping, "a") as f:
                f.write(f"{avg_ping} {mirror}\n")

        if not os.path.exists(tmp_ping):
            return None

        result = subprocess.run(["sort", "-n", tmp_ping], stdout=subprocess.PIPE, text=True)
        best_line = result.stdout.strip().splitlines()[0]
        os.remove(tmp_ping)
        return best_line.split(" ", 1)[1]

    @staticmethod
    def parse_ping_output(output):
        for line in output.splitlines():
            if "min/avg/max" in line:
                parts = line.split("/")
                try:
                    avg = float(parts[1])
                    return avg
                except (IndexError, ValueError):
                    pass
        return 9999

    def set_sources_list(self, mirror):
        sources_content = f"deb {mirror} kali-rolling main contrib non-free non-free-firmware\n"
        with open("/tmp/sources.list", "w") as f:
            f.write(sources_content)
        self.run_cmd("sudo mv /tmp/sources.list /etc/apt/sources.list")

    def run_cmd(self, cmd):
        self.log(f"Выполняется: {cmd}")
        process = subprocess.Popen(
            cmd.split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        self.current_process = process

        while process.poll() is None:
            line = process.stdout.readline()
            if line:
                self.log("   " + line.strip())

        # Читаем остаток вывода после завершения
        for line in process.stdout:
            self.log("   " + line.strip())

        self.current_process = None

        if process.returncode != 0:
            raise Exception(f"Команда завершена с ошибкой: {cmd}")

if __name__ == "__main__":
    # Если не в venv и не frozen — установим зависимости и перезапустимся
    if not os.getenv('VIRTUAL_ENV') and not sys.executable.endswith("venv/bin/python"):
        print("[INFO] Перезапуск внутри виртуального окружения...")
        install_dependencies()
        venv_python = os.path.join(venv_dir, "bin", "python")
        os.execl(venv_python, venv_python, os.path.abspath(sys.argv[0]))

    # Запуск GUI
    root = tk.Tk()
    app = MirrorApp(root)
    root.mainloop()

# keep_awake_mouse.py
import time
import threading
from pynput import mouse, keyboard

INTERVAL = 60  # ขยับทุก 60 วินาที

running = False
exit_flag = False

m = mouse.Controller()


def keep_awake_loop():
    global running, exit_flag

    while not exit_flag:
        if running:
            try:
                x, y = m.position
                m.position = (x + 1, y)
                time.sleep(0.2)
                m.position = (x, y)
                print("Moved mouse to prevent idle")
            except Exception as e:
                print("Loop error: {}".format(e))

            for _ in range(INTERVAL * 10):
                if exit_flag:
                    break
                if not running:
                    break
                time.sleep(0.1)
        else:
            time.sleep(0.1)


def on_press(key):
    global running, exit_flag

    if key == keyboard.Key.f6:
        running = not running
        print("Started" if running else "Stopped")

    elif key == keyboard.Key.f7:
        exit_flag = True
        print("Exiting...")
        return False


def main():
    print("=== Keep Awake Mouse ===")
    print("F6 = Start / Stop")
    print("F7 = Exit")

    t = threading.Thread(target=keep_awake_loop)
    t.daemon = True
    t.start()

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


if __name__ == "__main__":
    main()
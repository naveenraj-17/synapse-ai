import sys
import shutil
import subprocess
import webbrowser
import os
import time

def open_browser(url="http://localhost:3000"):
    print(f"Opening {url}...")
    
    # Browsers to try for "app" mode
    # Browsers to try for "app" mode
    browsers = ["google-chrome", "chromium", "brave-browser", "msedge"]
    
    # Check for WSL
    is_wsl = False
    if sys.platform == "linux":
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    is_wsl = True
        except:
            pass

    if is_wsl:
        browsers = [
            "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
            "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe",
            "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
        ]
    elif sys.platform == "darwin":
        browsers = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", 
                    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    elif sys.platform == "win32":
        browsers = ["chrome.exe", "msedge.exe"]
    
    browser_cmd = None
    for b in browsers:
        if shutil.which(b):
            browser_cmd = b
            break
        # Check absolute paths (macOS, WSL, Linux custom paths)
        if os.path.isabs(b) and os.path.exists(b):
            browser_cmd = b
            break
            
    if browser_cmd:
        print(f"Opening in app mode using {browser_cmd}...")
        try:
            subprocess.Popen([browser_cmd, f"--app={url}"])
            return
        except Exception as e:
            print(f"Failed to open in app mode: {e}")
    
    # Fallback
    print("Opening in default browser...")
    webbrowser.open(url)

if __name__ == "__main__":
    # Allow URL to be passed as argument
    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
    open_browser(target_url)

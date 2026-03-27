import os
import sys
import subprocess
import time
import platform
import shutil
import threading
import webbrowser
import launch_browser

# ANSI colors
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

def print_step(msg):
    print(f"\n{Colors.BLUE}{Colors.BOLD}==> {msg}{Colors.ENDC}")

def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.ENDC}")

def print_error(msg):
    print(f"{Colors.FAIL}✗ {msg}{Colors.ENDC}")

def check_command(command, helpful_msg=""):
    if shutil.which(command) is None:
        print_error(f"{command} not found. {helpful_msg}")
        return False
    return True

def install_backend():
    print_step("Setting up Backend...")
    
    venv_dir = os.path.join(BACKEND_DIR, "venv")
    if sys.platform == "win32":
        python_exe = os.path.join(venv_dir, "Scripts", "python.exe")
        pip_exe = os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        python_exe = os.path.join(venv_dir, "bin", "python")
        pip_exe = os.path.join(venv_dir, "bin", "pip")

    # Check for pip_exe to avoid broken venv states
    if not os.path.exists(pip_exe):
        if os.path.exists(venv_dir):
            print("Removing corrupted virtual environment...")
            shutil.rmtree(venv_dir)
            
        print("Creating virtual environment...")
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
    
    print("Installing requirements...")
    try:
        subprocess.check_call([pip_exe, "install", "-r", os.path.join(BACKEND_DIR, "requirements.txt")], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        print_success("Backend dependencies installed.")
    except subprocess.CalledProcessError:
        print_error("Failed to install backend dependencies. Check your requirements.txt.")
        sys.exit(1)
        
    return python_exe

def verify_backend_installation(python_exe):
    print_step("Verifying Python Modules...")
    
    # Python script to strictly test critical imports
    test_script = """
import sys
try:
    import fastapi
    import psycopg
    import psycopg_pool
    import chromadb
    import sqlalchemy
    import pypdf
    import bs4 # beautifulsoup4
except ImportError as e:
    print(str(e))
    sys.exit(1)
"""
    result = subprocess.run([python_exe, "-c", test_script], capture_output=True, text=True)
    
    if result.returncode != 0:
        print_error(f"Backend module validation failed!")
        print_error(f"Import Error: {result.stdout.strip() or result.stderr.strip()}")
        print(f"{Colors.WARNING}Please ensure your requirements.txt contains 'psycopg[binary]' instead of just 'psycopg'.{Colors.ENDC}")
        sys.exit(1)
        
    print_success("All critical backend modules verified.")

def install_frontend():
    print_step("Setting up Frontend...")
    
    if not check_command("npm", "Please install Node.js and npm."):
        sys.exit(1)
        
    print("Installing npm packages (this may take a while)...")
    try:
        shell_cmd = True if sys.platform == "win32" else False
        subprocess.check_call(["npm", "install"], cwd=FRONTEND_DIR, shell=shell_cmd,
                             stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        print_success("Frontend dependencies installed.")
    except subprocess.CalledProcessError:
        print_error("Failed to install frontend dependencies.")
        sys.exit(1)

def start_backend(python_exe):
    print_step("Starting Backend Server...")
    return subprocess.Popen([python_exe, "main.py"], cwd=BACKEND_DIR)

def start_frontend():
    print_step("Starting Frontend Server...")
    shell_cmd = True if sys.platform == "win32" else False
    return subprocess.Popen(["npm", "run", "dev"], cwd=FRONTEND_DIR, shell=shell_cmd)

def main():
    # 1. Hard Check for system dependencies BEFORE doing anything
    print_step("Checking System Dependencies...")
    if shutil.which("psql") is None:
        print_error("psql (PostgreSQL) is not installed on this system.")
        print(f"{Colors.WARNING}Coding agents require PostgreSQL and the pgvector extension to function.{Colors.ENDC}")
        print("Please install them and try again.")
        sys.exit(1)
    print_success("psql found.")

    # 2. Run Installations
    python_exe = install_backend()
    verify_backend_installation(python_exe) # NEW: Verifies imports actually work
    install_frontend()

    # 3. Start Servers
    backend_process = start_backend(python_exe)
    frontend_process = start_frontend()

    # 4. Launch Browser
    threading.Thread(target=launch_browser.open_browser).start()
    
    print(f"\n{Colors.GREEN}{Colors.BOLD}Application is running!{Colors.ENDC}")
    print(f"{Colors.WARNING}Press Ctrl+C to stop servers and exit.{Colors.ENDC}\n")
    
    # 5. Monitor Processes
    try:
        while True:
            time.sleep(1)
            if backend_process.poll() is not None:
                print_error("Backend crashed! Check terminal logs.")
                break
            
            if frontend_process.poll() is not None:
                print_error("Frontend crashed! Check terminal logs.")
                break
                
    except KeyboardInterrupt:
        print("\nStopping servers...")
        backend_process.terminate()
        
        if sys.platform != "win32":
             try:
                 os.killpg(os.getpgid(frontend_process.pid), 15)
             except:
                 frontend_process.terminate()
        else:
            frontend_process.terminate()
            
        print("Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()

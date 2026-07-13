# Micro VM Deployment

The Oracle `VM.Standard.E2.1.Micro` shape has about 1 GB RAM. It can run the core Discord bot, but Docker plus MySQL is tight. For this shape, prefer a lean deployment:

- Run Python directly in a virtual environment.
- Use `requirements-lean.txt`.
- Do not install OpenCV/Tesseract unless screenshot parsing is required.
- Add swap before installing packages.
- Prefer a small local MariaDB/MySQL service or move database work to a larger Always Free A1 VM when available.

## First Boot Hardening

Create extra swap before package installs:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Install minimal system packages:

```bash
sudo dnf -y install git python3 python3-pip
```

Clone and set up the app:

```bash
git clone --branch phase-0-baseline https://github.com/ashvinganesan/ClashRoyaleManager.git
cd ClashRoyaleManager
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-lean.txt
```

The database service still needs to be configured before the bot can run.

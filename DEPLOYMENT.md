# Chronos Engine v2.1 - Complete Deployment Guide

## 🚀 Production Deployment Checklist

### Pre-Deployment Setup

1. **Environment Preparation**
   ```bash
   # Clone the repository
   git clone <your-repo-url>
   cd chronos-engine

   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows

   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Configuration Setup**
   ```bash
   # Copy environment template
   cp .env.example .env

   # Edit configuration
   nano config/chronos.yaml
   nano .env
   ```

3. **Google Calendar Setup** (Optional but Recommended)
   - Follow `config/GOOGLE_CALENDAR_SETUP.md`
   - Place `credentials.json` in `config/` directory
   - Update `.env` with `GOOGLE_CALENDAR_ENABLED=true`

### Database Initialization

```bash
# Initialize database with Alembic
alembic upgrade head

# Verify database setup
python -c "from src.core.database import db_service; import asyncio; asyncio.run(db_service.create_tables())"
```

### Security Configuration

1. **API Key Setup**
   ```bash
   # Generate secure API key
   openssl rand -hex 32

   # Update in .env
   echo "CHRONOS_API_KEY=your-generated-key" >> .env
   ```

2. **Update config/chronos.yaml**
   ```yaml
   api:
     api_key: "your-secure-production-key"
     cors_origins: ["https://yourdomain.com"]
   ```

### Production Deployment Options

## Option 1: Docker Deployment (Recommended)

```bash
# Build and run
docker-compose up --build -d

# Check health
curl http://localhost:8080/health

# View logs
docker-compose logs -f chronos-app
```

## Option 2: Systemd Service (Linux)

1. **Create service file**
   ```bash
   sudo nano /etc/systemd/system/chronos.service
   ```

   ```ini
   [Unit]
   Description=Chronos Engine v2.1
   After=network.target

   [Service]
   Type=simple
   User=chronos
   WorkingDirectory=/opt/chronos-engine
   Environment=PATH=/opt/chronos-engine/venv/bin
   ExecStart=/opt/chronos-engine/venv/bin/python -m src.main
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

2. **Enable and start service**
   ```bash
   sudo systemctl enable chronos
   sudo systemctl start chronos
   sudo systemctl status chronos
   ```

## Option 3: Manual Process Manager

```bash
# Using screen
screen -S chronos
python -m src.main
# Ctrl+A, D to detach

# Using nohup
nohup python -m src.main > logs/chronos.log 2>&1 &
```

### Nginx Reverse Proxy Setup

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/chronos-engine/static/;
        expires 30d;
    }
}
```

### SSL/HTTPS Setup with Let's Encrypt

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal
sudo crontab -e
# Add: 0 12 * * * /usr/bin/certbot renew --quiet
```

### Monitoring and Logging

1. **Log Rotation Setup**
   ```bash
   sudo nano /etc/logrotate.d/chronos
   ```

   ```
   /opt/chronos-engine/logs/*.log {
       daily
       missingok
       rotate 52
       compress
       delaycompress
       notifempty
       create 644 chronos chronos
       postrotate
           systemctl reload chronos
       endscript
   }
   ```

2. **Health Check Monitoring**
   ```bash
   # Add to crontab
   */5 * * * * curl -f http://localhost:8080/health || systemctl restart chronos
   ```

### Backup Strategy

1. **Database Backup**
   ```bash
   # Daily backup script
   #!/bin/bash
   DATE=$(date +%Y%m%d_%H%M%S)
   cp data/chronos.db backups/chronos_${DATE}.db
   find backups/ -name "chronos_*.db" -mtime +30 -delete
   ```

2. **Configuration Backup**
   ```bash
   tar -czf config_backup_$(date +%Y%m%d).tar.gz config/ .env
   ```

### Performance Optimization

1. **Gunicorn for Production**
   ```bash
   pip install gunicorn

   # Run with gunicorn
   gunicorn src.main:create_app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8080
   ```

2. **Resource Limits**
   ```yaml
   # In docker-compose.yml
   services:
     chronos-app:
       deploy:
         resources:
           limits:
             memory: 512M
             cpus: '1.0'
   ```

### Troubleshooting Guide

**Common Issues:**

1. **Port already in use**
   ```bash
   sudo lsof -i :8080
   sudo kill -9 <PID>
   ```

2. **Permission errors**
   ```bash
   sudo chown -R chronos:chronos /opt/chronos-engine
   chmod +x start-chronos.bat
   ```

3. **Database locked**
   ```bash
   # Check for zombie processes
   ps aux | grep chronos
   # Kill if necessary
   ```

4. **Memory issues**
   ```bash
   # Monitor memory usage
   htop
   # Adjust worker count if needed
   ```

### Maintenance Tasks

**Daily:**
- Check logs for errors: `tail -f logs/chronos.log`
- Verify health endpoint: `curl http://localhost:8080/health`

**Weekly:**
- Review database size: `ls -lh data/`
- Check disk space: `df -h`
- Update dependencies: `pip list --outdated`

**Monthly:**
- Backup configuration and data
- Review and rotate logs
- Security updates: `pip install --upgrade -r requirements.txt`

### Production Checklist

- [ ] Environment variables configured
- [ ] Database initialized and migrated
- [ ] SSL certificates installed
- [ ] Firewall configured (ports 80, 443, 22)
- [ ] Monitoring and alerting set up
- [ ] Backup strategy implemented
- [ ] Log rotation configured
- [ ] Documentation updated
- [ ] Team access configured
- [ ] Health checks working

### Support and Maintenance

**Key Endpoints for Monitoring:**
- Health: `GET /health`
- Metrics: `GET /api/v1/analytics/productivity`
- Status: `GET /sync/status`

**Important Log Locations:**
- Application: `logs/chronos.log`
- System: `/var/log/syslog` (Linux)
- Nginx: `/var/log/nginx/access.log`

**Emergency Contacts:**
- System Administrator: [contact]
- Development Team: [contact]
- Hosting Provider: [contact]
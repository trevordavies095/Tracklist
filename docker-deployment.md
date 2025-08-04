# Docker Deployment Guide for Tracklist

This guide walks through containerizing the Tracklist application and deploying it using Portainer. The application supports bringing your own database and flexible database location configuration.

## Prerequisites

- Docker installed on your system
- Portainer running and accessible
- Basic familiarity with Docker containers
- (Optional) Existing Tracklist database file to import

## Step 1: Create Dockerfile

Create a `Dockerfile` in the project root:

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for database and config
RUN mkdir -p /app/data /app/config

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV TRACKLIST_DB_PATH=/app/data/tracklist.db
ENV HOST=0.0.0.0
ENV PORT=8000

# Run database initialization and start server
CMD ["sh", "-c", "python -c 'from app.database import init_db; init_db()' && uvicorn app.main:app --host ${HOST} --port ${PORT}"]
```

## Step 2: Create requirements.txt

Create a `requirements.txt` file with all dependencies:

```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
jinja2==3.1.2
python-multipart==0.0.6
httpx==0.25.2
python-dotenv==1.0.0
```

## Step 3: Create .dockerignore

Create a `.dockerignore` file to exclude unnecessary files:

```
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
.pytest_cache/
.coverage
htmlcov/
.tox/
.cache
.vscode/
.git/
.gitignore
*.md
Dockerfile
.dockerignore
*.log
.env
tracklist.db
```

## Step 4: Create Docker Compose File (Optional)

Create `docker-compose.yml` for easier local development:

```yaml
version: '3.8'

services:
  tracklist:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - tracklist_data:/app/data
      # Optional: Mount existing database
      # - /path/to/your/existing/tracklist.db:/app/data/tracklist.db
    environment:
      - TRACKLIST_DB_PATH=/app/data/tracklist.db
      - ENVIRONMENT=production
      - LOG_LEVEL=info
    restart: unless-stopped

volumes:
  tracklist_data:
```

## Step 5: Build Docker Image

### Option A: Build locally (No Registry Required)

```bash
# Build the image locally
docker build -t tracklist:latest .

# Verify the image was built
docker images | grep tracklist
```

### Option B: Build locally and push to registry

```bash
# Build the image
docker build -t tracklist:latest .

# Tag for your registry (replace with your registry)
docker tag tracklist:latest your-registry/tracklist:latest

# Push to registry
docker push your-registry/tracklist:latest
```

### Option C: Build directly in Portainer

You can build directly in Portainer using the Git repository (see Step 6).

## Step 6: Deploy in Portainer

### Method 1: Using Container Creation

1. **Access Portainer**: Open your Portainer web interface

2. **Navigate to Containers**: 
   - Go to your environment
   - Click on "Containers"
   - Click "Add container"

3. **Configure Container**:
   - **Name**: `tracklist`
   - **Image**: `your-registry/tracklist:latest` (or build from Git)
   - **Port mapping**: 
     - Host: `8000` → Container: `8000`

4. **Volume Configuration**:
   - Click "Add volume"
   - **Container path**: `/app/data`
   - **Volume**: Create new volume named `tracklist_data`
   
   **For existing database users**:
   - Alternative: Bind mount to existing database directory
   - **Container path**: `/app/data`
   - **Host path**: `/path/to/your/database/directory`

5. **Environment Variables**:
   - Add environment variables:
     - **Name**: `TRACKLIST_DB_PATH`
     - **Value**: `/app/data/tracklist.db` (or your preferred path)
     - **Name**: `ENVIRONMENT`
     - **Value**: `production`
     - **Name**: `LOG_LEVEL`
     - **Value**: `info`

6. **Restart Policy**:
   - Set to "Unless stopped"

7. **Deploy**: Click "Deploy the container"

### Method 2: Using Stack Deployment

1. **Navigate to Stacks**:
   - Go to "Stacks" in Portainer
   - Click "Add stack"

2. **Stack Configuration**:
   - **Name**: `tracklist-stack`
   - **Build method**: Choose one:

#### Option A: Web editor (Build from Git Repository)
Perfect for users without a registry! Paste this docker-compose.yml content:

```yaml
version: '3.8'

services:
  tracklist:
    # Build directly from Git repository
    build:
      context: https://github.com/your-username/tracklist.git
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - tracklist_data:/app/data
      # Optional: Mount existing database directory
      # - /host/path/to/database:/app/data
    environment:
      - TRACKLIST_DB_PATH=/app/data/tracklist.db
      - ENVIRONMENT=production
      - LOG_LEVEL=info
    restart: unless-stopped

volumes:
  tracklist_data:
```

#### Option A2: Web editor (Use Pre-built Image)
If you have access to a registry or built locally:

```yaml
version: '3.8'

services:
  tracklist:
    image: your-registry/tracklist:latest
    # OR use locally built image:
    # image: tracklist:latest
    ports:
      - "8000:8000"
    volumes:
      - tracklist_data:/app/data
      # Optional: Mount existing database directory  
      # - /host/path/to/database:/app/data
    environment:
      - TRACKLIST_DB_PATH=/app/data/tracklist.db
      - ENVIRONMENT=production
      - LOG_LEVEL=info
    restart: unless-stopped

volumes:
  tracklist_data:
```

#### Option B: Git Repository
- **Repository URL**: `https://github.com/your-username/tracklist.git`
- **Compose path**: `docker-compose.yml`
- **Auto-update**: Enable if desired

3. **Deploy Stack**: Click "Deploy the stack"

## Stack Deployment Without Registry

### Method 1: Build from Git Repository (Recommended)

This is the easiest method if you don't have a registry:

1. **Upload your code to Git** (GitHub, GitLab, etc.)
2. **In Portainer Stack Creation**:
   - Choose "Web editor"
   - Use this docker-compose.yml:

```yaml
version: '3.8'

services:
  tracklist:
    build:
      context: https://github.com/your-username/tracklist.git
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - tracklist_data:/app/data
    environment:
      - TRACKLIST_DB_PATH=/app/data/tracklist.db
      - ENVIRONMENT=production
      - LOG_LEVEL=info
    restart: unless-stopped

volumes:
  tracklist_data:
```

### Method 2: Build Locally Then Use in Stack

1. **Build image locally** on the Portainer host:
```bash
# SSH into your Portainer host
ssh user@your-portainer-host

# Clone the repository
git clone https://github.com/your-username/tracklist.git
cd tracklist

# Build the image
docker build -t tracklist:latest .
```

2. **Create stack in Portainer** using local image:
```yaml
version: '3.8'

services:
  tracklist:
    image: tracklist:latest
    ports:
      - "8000:8000"
    volumes:
      - tracklist_data:/app/data
    environment:
      - TRACKLIST_DB_PATH=/app/data/tracklist.db
      - ENVIRONMENT=production
      - LOG_LEVEL=info
    restart: unless-stopped

volumes:
  tracklist_data:
```

### Method 3: Private Git Repository

For private repositories, you'll need to set up authentication:

1. **Create deploy key or access token** in your Git provider
2. **Use Git repository option** in Portainer:
   - **Repository URL**: `https://username:token@github.com/your-username/tracklist.git`
   - **Compose path**: `docker-compose.yml`
   - **Auto-update**: Optional

Create this `docker-compose.yml` in your repository:
```yaml
version: '3.8'

services:
  tracklist:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - tracklist_data:/app/data
    environment:
      - TRACKLIST_DB_PATH=/app/data/tracklist.db
      - ENVIRONMENT=production
      - LOG_LEVEL=info
    restart: unless-stopped

volumes:
  tracklist_data:
```

## Step 7: Bringing Your Own Database

### Option A: Import Existing Database File

If you have an existing Tracklist SQLite database:

1. **Stop the container** if it's running
2. **Copy your database file** to the host system
3. **Update the container configuration**:
   - In Portainer, edit the container
   - Update volume mount to point to your database directory
   - Or replace the volume content with your database

```bash
# Example: Copy your database to Docker volume
docker cp /path/to/your/tracklist.db container_name:/app/data/tracklist.db
```

### Option B: Mount External Database Directory

For existing database in a specific location:

1. **In Portainer Container Configuration**:
   - Remove the Docker volume
   - Add bind mount:
     - **Container path**: `/app/data`
     - **Host path**: `/absolute/path/to/your/database/directory`

2. **Environment Variables**:
   - Set `TRACKLIST_DB_PATH=/app/data/your-database-name.db`

### Option C: Custom Database Path

To use a database in a different location:

1. **Add Environment Variable**:
   - **Name**: `TRACKLIST_DB_PATH`
   - **Value**: `/custom/path/to/database.db`

2. **Mount the directory**:
   - Ensure the custom path is mounted as a volume
   - Container path: `/custom/path` (or parent directory)
   - Host path: Your host directory containing the database

## Step 8: Access Application

1. **Check Container Status**: Verify container is running in Portainer
2. **Access Application**: Open `http://your-server-ip:8000`
3. **Verify Database**: Check `/api/v1/system/info` endpoint for database info
4. **Test Functionality**: Verify all features work correctly

## Step 9: Production Considerations

### Environment Variables

For production, consider adding these environment variables:

```yaml
environment:
  # Database Configuration
  - TRACKLIST_DB_PATH=/app/data/tracklist.db
  
  # Application Settings
  - ENVIRONMENT=production
  - LOG_LEVEL=info
  - SECRET_KEY=your-secret-key-here
  
  # MusicBrainz API Configuration
  - MUSICBRAINZ_USER_AGENT=Tracklist/1.0 (your-email@example.com)
  - MUSICBRAINZ_RATE_LIMIT=1.0
  
  # Server Configuration
  - HOST=0.0.0.0
  - PORT=8000
  - WORKERS=1
```

### Database Configuration Examples

#### Using Custom Database Location
```yaml
environment:
  - TRACKLIST_DB_PATH=/music/databases/my-tracklist.db
volumes:
  - /host/music/databases:/music/databases
```

#### Using Environment-Specific Databases
```yaml
environment:
  - TRACKLIST_DB_PATH=/app/data/${ENVIRONMENT:-production}-tracklist.db
```

#### Using Full Database URL (Advanced)
```yaml
environment:
  - DATABASE_URL=sqlite:///app/data/custom-name.db
  # or for external databases:
  - DATABASE_URL=postgresql://user:pass@db-host:5432/tracklist
```

### Reverse Proxy Setup

For production deployment with domain name, set up a reverse proxy:

#### Nginx Configuration Example:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### Traefik Labels (if using Traefik):

```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.tracklist.rule=Host(`your-domain.com`)"
  - "traefik.http.services.tracklist.loadbalancer.server.port=8000"
```

### SSL/HTTPS

For HTTPS, you can:
1. Use Traefik with Let's Encrypt
2. Use Nginx with Certbot
3. Use Cloudflare SSL

### Database Backup

Set up regular backups of the SQLite database:

```bash
# Create backup script
#!/bin/bash
CONTAINER_NAME="tracklist"
BACKUP_DIR="/host/backups"
DB_PATH="/app/data/tracklist.db"

# Create backup with timestamp
docker exec $CONTAINER_NAME cp $DB_PATH /app/data/backup-$(date +%Y%m%d-%H%M%S).db

# Or copy to host system
docker cp $CONTAINER_NAME:$DB_PATH $BACKUP_DIR/tracklist-backup-$(date +%Y%m%d-%H%M%S).db

# Add to crontab for daily backups
# 0 2 * * * /path/to/backup-script.sh
```

### Database Migration from CLI Tool

If migrating from the CLI version:

1. **Use the migration script** (included in the repository):
```bash
# Copy CLI database to container
docker cp /path/to/cli-database.db container_name:/app/data/cli-database.db

# Run migration inside container
docker exec -it container_name python migrate_cli_to_webui.py /app/data/cli-database.db
```

2. **Or mount CLI database and migrate**:
```yaml
volumes:
  - /path/to/cli/database:/app/cli-data:ro
  - tracklist_data:/app/data
environment:
  - TRACKLIST_DB_PATH=/app/data/tracklist.db
```

## Step 10: Monitoring and Logs

### View Logs in Portainer
1. Go to container details
2. Click "Logs" tab
3. Monitor application logs

### Health Check (Optional)

Add health check to Dockerfile:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1
```

## Troubleshooting

### Common Issues

1. **Container won't start**:
   - Check logs in Portainer
   - Verify port availability
   - Check environment variables

2. **Database issues**:
   - Ensure volume is mounted correctly
   - Check permissions on `/app/data`
   - Verify DATABASE_URL format

3. **Static files not loading**:
   - Ensure `static/` directory is included in build
   - Check file permissions

4. **MusicBrainz API not working**:
   - Verify internet connectivity from container
   - Check firewall rules

### Useful Commands

```bash
# View container logs
docker logs tracklist

# Execute commands in container
docker exec -it tracklist bash

# Check container resource usage
docker stats tracklist

# Check database info via API
curl http://localhost:8000/api/v1/system/info

# View current database path
docker exec tracklist python -c "from app.database import get_db_info; import json; print(json.dumps(get_db_info(), indent=2))"

# Update container
docker pull your-registry/tracklist:latest
docker stop tracklist
docker rm tracklist
# Then redeploy in Portainer
```

## Security Considerations

1. **Use non-root user** in container
2. **Set resource limits** in Portainer
3. **Use secrets** for sensitive data
4. **Regular updates** of base image and dependencies
5. **Network isolation** if needed

## Updates and Maintenance

### Updating the Application

1. Build new image with updated code
2. Push to registry
3. In Portainer:
   - Stop existing container
   - Update image reference
   - Start container
   - Or use stack update for zero-downtime updates

### Database Migrations

For future database schema changes:

```dockerfile
# Add migration command before server start
CMD ["sh", "-c", "python -c 'from app.database import init_db; init_db()' && python migrate.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

This guide provides a complete walkthrough for containerizing and deploying the Tracklist application using Docker and Portainer.
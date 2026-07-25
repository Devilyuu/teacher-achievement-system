# Chengguo Subdomain and Portfolio Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the existing teacher achievement system at `https://chengguo.youpulab.com` and link the live application from the YoupuLab homepage and works page.

**Architecture:** DNSPod resolves the dedicated subdomain to the existing Tencent Lighthouse server. A dedicated Nginx virtual host terminates HTTPS and proxies requests to the existing FastAPI service on `127.0.0.1:8001`, so databases and uploaded materials remain unchanged. The YoupuLab Astro site reads one shared work record, so changing its status and link updates both site entry points.

**Tech Stack:** DNSPod, Nginx, Let's Encrypt Certbot, FastAPI/Uvicorn, Astro, GitHub Actions, PowerShell, SSH.

---

## File Structure

Teacher achievement repository:

- Create `deploy/nginx/chengguo-http.conf`: certificate bootstrap virtual host.
- Create `deploy/nginx/chengguo.youpulab.com.conf`: final HTTPS reverse-proxy virtual host.
- Modify `docs/superpowers/plans/2026-07-25-chengguo-subdomain-and-portfolio-link.md`: check completed steps during execution.

YoupuLab repository:

- Modify `src/data/works.json`: mark the teacher achievement project live and assign the public URL.

Server:

- Create `/etc/nginx/sites-available/chengguo`.
- Create symlink `/etc/nginx/sites-enabled/chengguo`.
- Create certificate files through Certbot under `/etc/letsencrypt/live/chengguo.youpulab.com/`.

### Task 1: Establish DNS

- [ ] **Step 1: Add the DNSPod record**

Create this DNS record in the `youpulab.com` zone:

```text
Host: chengguo
Type: A
Value: 124.221.239.254
TTL: 600
```

- [ ] **Step 2: Verify public resolution**

Run:

```powershell
Resolve-DnsName chengguo.youpulab.com -Type A
```

Expected: an A record whose `IPAddress` is `124.221.239.254`.

- [ ] **Step 3: Verify no existing conflicting server block**

Run:

```powershell
ssh -i "$env:USERPROFILE\.ssh\teacher_achievement_tencent_ed25519" ubuntu@124.221.239.254 "sudo nginx -T 2>/dev/null | grep -n 'chengguo.youpulab.com' || true"
```

Expected before rollout: no matching active server block.

### Task 2: Add Reproducible Nginx Configuration

**Files:**

- Create: `deploy/nginx/chengguo-http.conf`
- Create: `deploy/nginx/chengguo.youpulab.com.conf`

- [ ] **Step 1: Create the certificate bootstrap config**

Create `deploy/nginx/chengguo-http.conf`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name chengguo.youpulab.com;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/youpulab;
        default_type "text/plain";
    }

    location / {
        return 404;
    }
}
```

The bootstrap host exposes only the ACME challenge path. Every other HTTP request returns `404`, so the application is not served over HTTP before the certificate is installed.

- [ ] **Step 2: Create the final HTTPS config**

Create `deploy/nginx/chengguo.youpulab.com.conf`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name chengguo.youpulab.com;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/youpulab;
        default_type "text/plain";
    }

    location / {
        return 301 https://chengguo.youpulab.com$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name chengguo.youpulab.com;

    ssl_certificate /etc/letsencrypt/live/chengguo.youpulab.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/chengguo.youpulab.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 64m;

    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Content-Security-Policy "frame-ancestors 'self'" always;

    location /static/ {
        alias /opt/teacher-achievement-system/app/static/;
        expires 7d;
        add_header Cache-Control "public";
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Strict-Transport-Security "max-age=31536000" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header Content-Security-Policy "frame-ancestors 'self'" always;
    }

    location = /materials/upload {
        client_max_body_size 512m;
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

The application accepts at most 10 files per batch, with a 50 MB per-file limit and a 500 MB aggregate limit. Nginx allows 512 MB only on the exact `/materials/upload` route to leave room for multipart overhead; replacement uploads and every other HTTPS route use the 64 MB default.

- [ ] **Step 3: Inspect the tracked configs**

Run:

```powershell
rg -n "server_name|proxy_pass|ssl_certificate|client_max_body_size" deploy/nginx
```

Expected: both configs target only `chengguo.youpulab.com`, only the final config proxies to port 8001, and the final config references the dedicated certificate.

- [ ] **Step 4: Commit the infrastructure templates**

Run:

```powershell
git add deploy/nginx/chengguo-http.conf deploy/nginx/chengguo.youpulab.com.conf
git commit -m "ops: add chengguo nginx configuration"
```

Expected: one commit containing only the two Nginx templates.

### Task 3: Publish the Subdomain and Certificate

- [ ] **Step 1: Upload and enable the bootstrap config**

Run from the teacher achievement repository:

```powershell
scp -i "$env:USERPROFILE\.ssh\teacher_achievement_tencent_ed25519" deploy/nginx/chengguo-http.conf ubuntu@124.221.239.254:/tmp/chengguo-http.conf
ssh -i "$env:USERPROFILE\.ssh\teacher_achievement_tencent_ed25519" ubuntu@124.221.239.254 "sudo install -m 0644 /tmp/chengguo-http.conf /etc/nginx/sites-available/chengguo && sudo ln -sfn /etc/nginx/sites-available/chengguo /etc/nginx/sites-enabled/chengguo && sudo nginx -t && sudo systemctl reload nginx"
```

Expected: `nginx -t` reports successful syntax and configuration.

- [ ] **Step 2: Verify bootstrap HTTP exposes only ACME**

Run:

```powershell
curl.exe -I http://chengguo.youpulab.com/login
```

Expected: Nginx returns `404`; the FastAPI application is not exposed through the bootstrap HTTP host.

- [ ] **Step 3: Request the certificate**

Run:

```powershell
ssh -i "$env:USERPROFILE\.ssh\teacher_achievement_tencent_ed25519" ubuntu@124.221.239.254 "sudo certbot certonly --webroot -w /var/www/youpulab -d chengguo.youpulab.com --non-interactive --agree-tos --keep-until-expiring"
```

Expected: Certbot reports a valid certificate stored under `/etc/letsencrypt/live/chengguo.youpulab.com/`.

- [ ] **Step 4: Upload and enable the final HTTPS config**

Run:

```powershell
scp -i "$env:USERPROFILE\.ssh\teacher_achievement_tencent_ed25519" deploy/nginx/chengguo.youpulab.com.conf ubuntu@124.221.239.254:/tmp/chengguo.youpulab.com.conf
ssh -i "$env:USERPROFILE\.ssh\teacher_achievement_tencent_ed25519" ubuntu@124.221.239.254 "sudo install -m 0644 /tmp/chengguo.youpulab.com.conf /etc/nginx/sites-available/chengguo && sudo nginx -t && sudo systemctl reload nginx"
```

Expected: Nginx reload succeeds without restarting the FastAPI application.

- [ ] **Step 5: Verify certificate renewal configuration**

Run:

```powershell
ssh -i "$env:USERPROFILE\.ssh\teacher_achievement_tencent_ed25519" ubuntu@124.221.239.254 "sudo certbot renew --dry-run"
```

Expected: the dry run succeeds for the YoupuLab and Chengguo certificates.

### Task 4: Validate the Achievement System Through HTTPS

- [ ] **Step 1: Verify redirect and health**

Run:

```powershell
curl.exe -I http://chengguo.youpulab.com/
curl.exe -I https://chengguo.youpulab.com/login
curl.exe https://chengguo.youpulab.com/health
```

Expected:

- HTTP redirects to HTTPS.
- `/login` returns `200`.
- `/health` returns the application health payload.

- [ ] **Step 2: Run an authenticated browser smoke test**

Open `https://chengguo.youpulab.com/login`, sign in with the existing administrator test account, and verify:

```text
Annual dashboard loads
Achievement list loads
New achievement form loads
Materials page loads
Export history loads
Logout returns to /login on the same hostname
```

- [ ] **Step 3: Verify existing routes remain available**

Run:

```powershell
curl.exe -I https://www.youpulab.com/
curl.exe -I http://124.221.239.254/login
```

Expected: YoupuLab remains `200`; direct IP access still reaches the achievement system during the transition.

### Task 5: Link YoupuLab to the Live Application

**Files:**

- Modify: `C:\Users\lenovo\Desktop\youpulab\src\data\works.json`

- [ ] **Step 1: Clone and verify the website repository**

Run:

```powershell
git clone https://github.com/Devilyuu/youpulab.git C:\Users\lenovo\Desktop\youpulab
git -C C:\Users\lenovo\Desktop\youpulab status --short
```

Expected: the private repository clones successfully and the worktree is clean.

- [ ] **Step 2: Update the shared work record**

Change only the `teacher-stats` entry:

```json
{
  "id": "teacher-stats",
  "name": "教师成果统计系统",
  "featured": true,
  "category": "teach",
  "emoji": "📊",
  "cover": "c1",
  "image": "/covers/teacher-stats.png",
  "desc": "教学科研成果一站式统计与可视化，年终汇总不再翻箱倒柜。",
  "highlights": ["成果录入与分类", "自动汇总报表", "可视化图表"],
  "tags": ["AI", "Web", "数据可视化"],
  "status": "live",
  "link": "https://chengguo.youpulab.com"
}
```

- [ ] **Step 3: Install and build**

Run:

```powershell
npm ci
npm run build
```

Working directory: `C:\Users\lenovo\Desktop\youpulab`

Expected: Astro build succeeds with no errors.

- [ ] **Step 4: Verify both generated entry points**

Run:

```powershell
rg -n "chengguo\.youpulab\.com|已上线|在线体验" dist/index.html dist/works/index.html
```

Expected: both files contain the public URL and live presentation.

- [ ] **Step 5: Commit and push the website**

Run:

```powershell
git add src/data/works.json
git commit -m "feat: link live teacher achievement system"
git push origin main
```

Expected: the push succeeds and starts the existing GitHub Actions deployment workflow.

### Task 6: Final Production Verification

- [ ] **Step 1: Check the YoupuLab deployment workflow**

Run:

```powershell
gh run list --repo Devilyuu/youpulab --workflow deploy.yml --limit 1
```

Expected: the most recent workflow for the website commit completes successfully.

- [ ] **Step 2: Verify the production pages**

Open:

```text
https://www.youpulab.com/
https://www.youpulab.com/works/
```

Expected on both pages:

- “教师成果统计系统” shows “已上线”.
- The action reads “在线体验”.
- The link target is `https://chengguo.youpulab.com`.

- [ ] **Step 3: Verify the complete navigation**

Click “在线体验” from each page.

Expected: a new tab opens the HTTPS teacher achievement login page with a valid certificate.

- [ ] **Step 4: Run regression checks**

Run in the teacher achievement repository:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected: all tests pass; only the persistent untracked `docs/prototype/screenshots/` directory remains unrelated.

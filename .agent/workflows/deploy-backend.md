---
description: Deploy Backend to Production
---

This workflow automates the pulling of changes, database migrations, and service restarts for the Django backend on the production EC2 server.

// turbo-all
1. Pull latest changes
   If the server is on `main`, you can pull from `production` to merge:
   ```bash
   ssh -i "~/Downloads/IB-keypair.pem" ubuntu@ec2-98-84-2-236.compute-1.amazonaws.com "cd Projects/GHL-Custom-order-and-invoice && git pull origin production"
   ```
   *Note: It is recommended to switch the server branch to `production` permanently using `git checkout production`.*

2. Run database migrations
   ```bash
   ssh -i "~/Downloads/IB-keypair.pem" ubuntu@ec2-98-84-2-236.compute-1.amazonaws.com "cd Projects/GHL-Custom-order-and-invoice && python3 manage.py migrate"
   ```

3. Restart the Djangoproject service
   ```bash
   ssh -i "~/Downloads/IB-keypair.pem" ubuntu@ec2-98-84-2-236.compute-1.amazonaws.com "sudo systemctl restart djangoproject.service"
   ```

> [!IMPORTANT]
> Always verify that your local changes are pushed to the `production` branch on GitHub before running this workflow.

# Deploying to AWS ECS Fargate

This guide deploys the QA Command Center (Dashboard + Worker) to AWS ECS Fargate as two services with a shared EFS volume for reports.

## Prerequisites

- AWS account with ECS, ECR, EFS, and Secrets Manager access
- AWS CLI v2 installed and configured
- Docker installed locally

## 1. Set Variables

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_DASHBOARD=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/qa-dashboard
export ECR_WORKER=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/qa-worker
export CLUSTER_NAME=qa-command-center
```

## 2. Create ECR Repositories

```bash
aws ecr create-repository --repository-name qa-dashboard --region ${AWS_REGION}
aws ecr create-repository --repository-name qa-worker --region ${AWS_REGION}
```

## 3. Build and Push Images

```bash
# Authenticate Docker to ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

# Build from project root
docker build -f qa_agent/dashboard/Dockerfile -t ${ECR_DASHBOARD}:latest .
docker build -f qa_agent/dashboard/Dockerfile.worker -t ${ECR_WORKER}:latest .

# Push
docker push ${ECR_DASHBOARD}:latest
docker push ${ECR_WORKER}:latest
```

## 4. Create Secrets

```bash
aws secretsmanager create-secret \
  --name qa-agent/ANTHROPIC_API_KEY \
  --secret-string "sk-ant-..."
```

## 5. Create EFS Volume (Shared Storage)

```bash
# Create EFS file system
EFS_ID=$(aws efs create-file-system \
  --performance-mode generalPurpose \
  --throughput-mode bursting \
  --tags Key=Name,Value=qa-reports \
  --query 'FileSystemId' --output text)

# Create mount targets in each subnet
aws efs create-mount-target \
  --file-system-id ${EFS_ID} \
  --subnet-id subnet-xxxxx \
  --security-groups sg-xxxxx

# Create access point
AP_ID=$(aws efs create-access-point \
  --file-system-id ${EFS_ID} \
  --root-directory "Path=/data,CreationInfo={OwnerUid=1000,OwnerGid=1000,Permissions=755}" \
  --query 'AccessPointId' --output text)
```

## 6. Create ECS Cluster

```bash
aws ecs create-cluster \
  --cluster-name ${CLUSTER_NAME} \
  --capacity-providers FARGATE FARGATE_SPOT
```

## 7. Create Task Execution Role

```bash
# Create role
aws iam create-role \
  --role-name qa-ecs-task-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach policies
aws iam attach-role-policy \
  --role-name qa-ecs-task-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Grant Secrets Manager access
aws iam put-role-policy \
  --role-name qa-ecs-task-role \
  --policy-name SecretsAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:'${AWS_REGION}':'${AWS_ACCOUNT_ID}':secret:qa-agent/*"
    }]
  }'
```

## 8. Task Definitions

### Dashboard Task Definition (`task-def-dashboard.json`)

```json
{
  "family": "qa-dashboard",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/qa-ecs-task-role",
  "containerDefinitions": [{
    "name": "dashboard",
    "image": "ACCOUNT.dkr.ecr.REGION.amazonaws.com/qa-dashboard:latest",
    "portMappings": [{"containerPort": 8080, "protocol": "tcp"}],
    "environment": [
      {"name": "DATA_DIR", "value": "/data"},
      {"name": "WORKER_URL", "value": "http://worker.qa-local:8081"}
    ],
    "mountPoints": [{"sourceVolume": "reports", "containerPath": "/data"}],
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
      "interval": 10,
      "timeout": 3,
      "retries": 3,
      "startPeriod": 10
    },
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/qa-dashboard",
        "awslogs-region": "REGION",
        "awslogs-stream-prefix": "dashboard"
      }
    }
  }],
  "volumes": [{
    "name": "reports",
    "efsVolumeConfiguration": {
      "fileSystemId": "fs-xxxxx",
      "transitEncryption": "ENABLED",
      "authorizationConfig": {"accessPointId": "fsap-xxxxx", "iam": "ENABLED"}
    }
  }]
}
```

### Worker Task Definition (`task-def-worker.json`)

```json
{
  "family": "qa-worker",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "2048",
  "memory": "4096",
  "executionRoleArn": "arn:aws:iam::ACCOUNT:role/qa-ecs-task-role",
  "containerDefinitions": [{
    "name": "worker",
    "image": "ACCOUNT.dkr.ecr.REGION.amazonaws.com/qa-worker:latest",
    "portMappings": [{"containerPort": 8081, "protocol": "tcp"}],
    "environment": [
      {"name": "DATA_DIR", "value": "/data"},
      {"name": "PROJECT_ROOT", "value": "/app"},
      {"name": "DASHBOARD_URL", "value": "http://dashboard.qa-local:8080"}
    ],
    "secrets": [{
      "name": "ANTHROPIC_API_KEY",
      "valueFrom": "arn:aws:secretsmanager:REGION:ACCOUNT:secret:qa-agent/ANTHROPIC_API_KEY"
    }],
    "mountPoints": [{"sourceVolume": "reports", "containerPath": "/data"}],
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8081/health || exit 1"],
      "interval": 10,
      "timeout": 3,
      "retries": 3,
      "startPeriod": 30
    },
    "stopTimeout": 120,
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/qa-worker",
        "awslogs-region": "REGION",
        "awslogs-stream-prefix": "worker"
      }
    }
  }],
  "volumes": [{
    "name": "reports",
    "efsVolumeConfiguration": {
      "fileSystemId": "fs-xxxxx",
      "transitEncryption": "ENABLED",
      "authorizationConfig": {"accessPointId": "fsap-xxxxx", "iam": "ENABLED"}
    }
  }]
}
```

## 9. Create Services with Service Discovery

```bash
# Create namespace for service discovery
aws servicediscovery create-private-dns-namespace \
  --name qa-local \
  --vpc vpc-xxxxx

# Register services
aws ecs create-service \
  --cluster ${CLUSTER_NAME} \
  --service-name dashboard \
  --task-definition qa-dashboard \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --service-registries "registryArn=arn:aws:servicediscovery:...:service/srv-xxx"

aws ecs create-service \
  --cluster ${CLUSTER_NAME} \
  --service-name worker \
  --task-definition qa-worker \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --service-registries "registryArn=arn:aws:servicediscovery:...:service/srv-xxx"
```

## 10. Add ALB for Dashboard

```bash
# Create target group
aws elbv2 create-target-group \
  --name qa-dashboard-tg \
  --protocol HTTP \
  --port 8080 \
  --vpc-id vpc-xxxxx \
  --target-type ip \
  --health-check-path /health

# Attach to ALB listener (assumes ALB exists)
aws elbv2 create-rule \
  --listener-arn arn:aws:elasticloadbalancing:...:listener/... \
  --conditions Field=host-header,Values=qa.yourcompany.com \
  --actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...:targetgroup/qa-dashboard-tg/...
```

## Cost Estimate

| Component | Spec | Monthly Cost (est.) |
|-----------|------|-------------------|
| Dashboard | 0.25 vCPU, 512MB, 1 task | ~$10 |
| Worker | 2 vCPU, 4GB, 1 task | ~$70 |
| EFS | 1GB stored | ~$0.30 |
| ECR | 2 images (~2GB) | ~$0.20 |
| Secrets Manager | 1 secret | ~$0.40 |
| ALB | 1 load balancer | ~$18 |
| **Total** | | **~$99/month** |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Worker can't reach dashboard | Check security group rules and service discovery |
| EFS mount fails | Verify mount targets exist in the same subnet |
| Secret not found | Check IAM role has secretsmanager:GetSecretValue |
| Worker OOM killed | Increase task memory (4GB recommended) |
| Long eval timeout | Set `stopTimeout: 120` in task definition |

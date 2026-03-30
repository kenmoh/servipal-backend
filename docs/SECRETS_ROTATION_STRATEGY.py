"""
Secrets management and rotation strategy for ServiPal.

Production deployment options:
1. AWS Secrets Manager - Recommended
2. Google Cloud Secret Manager
3. HashiCorp Vault
4. Manual rotation with Git-based versioning

This file documents the rotation strategy and scripts needed.
"""

# =============================================================================
# SECRETS ROTATION PLAYBOOK
# =============================================================================

SECRETS_TO_ROTATE = {
    "INTERNAL_API_KEY": {
        "frequency": "quarterly",  # Every 3 months
        "criticality": "high",
        "rotation_strategy": "zero-downtime",
        "impact": "All internal service communications",
    },
    "FLW_SECRET_HASH": {
        "frequency": "quarterly",
        "criticality": "critical",  # Payment provider
        "rotation_strategy": "manual via Flutterwave dashboard",
        "impact": "Webhook validation",
    },
    "SUPABASE_SECRET_KEY": {
        "frequency": "semi-annually",
        "criticality": "critical",  # Database admin access
        "rotation_strategy": "via Supabase console",
        "impact": "All admin database operations",
    },
    "FLW_PROD_SECRET_KEY": {
        "frequency": "quarterly",
        "criticality": "critical",  # Payment processing
        "rotation_strategy": "manual + update in code",
        "impact": "Payment transaction signing",
    },
}

# =============================================================================
# OPTION 1: AWS SECRETS MANAGER (RECOMMENDED FOR PRODUCTION)
# =============================================================================

# Setup command (one-time):
"""
# Install AWS CLI
pip install boto3

# Create secret in AWS Secrets Manager
aws secretsmanager create-secret \
    --name servipal/production/internal-api-key \
    --description "ServiPal Internal API Key" \
    --secret-string '{"key":"YOUR_KEY_HERE"}'

# Configure rotation in AWS console:
# - Enable automatic rotation
# - Set rotation to 90 days
# - Lambda: Rotate on schedule
"""

# Python code to fetch from AWS Secrets Manager:
AWS_SECRETS_FETCH = """
import boto3
import json

def get_secret_from_aws(secret_name: str, region: str = "us-east-1"):
    '''Fetch secret from AWS Secrets Manager'''
    client = boto3.client('secretsmanager', region_name=region)
    
    try:
        response = client.get_secret_value(SecretId=secret_name)
        
        if 'SecretString' in response:
            return json.loads(response['SecretString'])
        else:
            return response['SecretBinary']
    except Exception as e:
        print(f"Error fetching secret {secret_name}: {e}")
        return None

# Usage in config:
# Add to app/config/config.py
def load_secrets():
    if settings.ENVIRONMENT == "production":
        internal_key = get_secret_from_aws("servipal/production/internal-api-key")
        settings.INTERNAL_API_KEY = internal_key["key"]
"""

# =============================================================================
# OPTION 2: MANUAL ROTATION WITH VERSION CONTROL
# =============================================================================

MANUAL_ROTATION_SCRIPT = """
#!/bin/bash
# scripts/rotate-secrets.sh

set -e

ENVIRONMENT=${1:-staging}
SECRET_NAME=${2:-INTERNAL_API_KEY}

echo "🔄 Rotating secret: $SECRET_NAME in $ENVIRONMENT"

# 1. Generate new secret
NEW_SECRET=$(openssl rand -base64 32)

# 2. Update .env.production or use your deployment tool
echo "New secret: $NEW_SECRET"

# 3. Create a temporary .env with new secret
echo "$SECRET_NAME=$NEW_SECRET" >> .env.$ENVIRONMENT.tmp

# 4. Validate before deploying
echo "✓ Validate the new secret works with your credentials"

# 5. Update in your deployment system (AWS Parameter Store, etc.)
# aws ssm put-parameter \\
#     --name /servipal/$ENVIRONMENT/$SECRET_NAME \\
#     --value "$NEW_SECRET" \\
#     --overwrite

# 6. Deploy new version
# docker build -t servipal:latest .
# docker push servipal:latest

# 7. Rotate pod to load new secret
# kubectl rollout restart deployment/servipal -n production

echo "✅ Secret rotated. Old secret is still valid for 24 hours (grace period)"
echo "   Schedule removal of old secret after verification"
"""

# =============================================================================
# OPTION 3: HASHICORP VAULT (MOST SECURE FOR LARGE DEPLOYMENTS)
# =============================================================================

VAULT_CONFIG = """
# docker-compose.yml addition for Vault:

vault:
  image: vault:latest
  environment:
    VAULT_DEV_ROOT_TOKEN_ID: "dev-token-12345"
    VAULT_DEV_LISTEN_ADDRESS: "0.0.0.0:8200"
  ports:
    - "8200:8200"
  volumes:
    - vault_data:/vault/data

volumes:
  vault_data:

# Python client for Vault:
import hvac

client = hvac.Client(url='http://localhost:8200', token='dev-token-12345')

# Read secret
secret = client.secrets.kv.read_secret_version(
    path='servipal/internal-api-key'
)

# Write/update secret (rotation)
client.secrets.kv.create_or_update_secret(
    path='servipal/internal-api-key',
    secret_dict={'value': new_api_key}
)

# Automatic rotation policy
# Vault can enforce rotation every 90 days
"""

# =============================================================================
# ROTATION CHECKLIST
# =============================================================================

ROTATION_CHECKLIST = """
☐ BEFORE ROTATION:
  ☐ Notify all services using the secret
  ☐ Create backup of current secret
  ☐ Test new secret in staging environment
  ☐ Check all dependent services

☐ DURING ROTATION:
  ☐ Generate new cryptographically secure secret
  ☐ Update in secrets manager (AWS/Vault)
  ☐ Update in environment configuration
  ☐ Deploy to production
  ☐ Verify applications can read new secret
  ☐ Monitor logs for authentication failures

☐ AFTER ROTATION:
  ☐ Keep old secret valid for 24 hours (grace period)
  ☐ Verify no services are using old secret
  ☐ Revoke/delete old secret
  ☐ Document rotation in audit log
  ☐ Schedule next rotation (90 days)

☐ MONITORING:
  ☐ Alert on failed secret reads
  ☐ Alert on authentication failures
  ☐ Audit who accessed secrets
"""

# =============================================================================
# IMMEDIATE IMPLEMENTATION (NO EXTERNAL SERVICES)
# =============================================================================

IMMEDIATE_STEPS = """
1. Generate strong API keys (minimum 32 bytes):
   python -c "import secrets; print(secrets.token_urlsafe(32))"

2. Store in .env.production (NEVER commit):
   INTERNAL_API_KEY=Drmhze6EPcv0fN_81Bj-nA_...
   FLW_PROD_SECRET_KEY=xxxxxxxxxxxxxxxxxxx

3. Set up Git pre-commit hook to prevent accidental commits:
   cat > .git/hooks/pre-commit << 'EOF'
   #!/bin/bash
   if git diff --cached | grep -E "INTERNAL_API_KEY|SECRET_KEY"; then
       echo "ERROR: Secrets detected in commit!"
       exit 1
   fi
   EOF
   chmod +x .git/hooks/pre-commit

4. Add rotation reminder (cron):
   # Rotate secrets every 90 days
   0 0 1 */3 * /path/to/scripts/rotate-secrets.sh production

5. Enable audit logging:
   - Track who accessed secrets
   - Track when secrets were rotated
   - Track failed authentication attempts
"""

# =============================================================================
# RECOMMENDED PRODUCTION SETUP (6 MONTHS)
# =============================================================================

RECOMMENDED_PRODUCTION = """
Phase 1 (Month 1):
- Deploy with manual rotation scripts
- Set up Git pre-commit hooks
- Add secret access logging

Phase 2 (Month 2-3):
- Migrate to AWS Secrets Manager
- Enable automatic rotation Lambda
- Set up rotation alerts

Phase 3 (Month 4-6):
- Implement HashiCorp Vault for developers
- Set up Vault Agent-based secret injection
- Enable comprehensive audit logging
"""

print(__doc__)

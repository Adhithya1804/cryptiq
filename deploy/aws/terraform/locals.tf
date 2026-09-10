locals {
  name_prefix = lower("${var.project_name}-${var.environment}")

  default_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "Terraform"
  }

  log_groups = {
    backend   = "/cryptiq/backend"
    frontend  = "/cryptiq/frontend"
    nginx     = "/cryptiq/nginx"
    bootstrap = "/cryptiq/bootstrap"
  }

  ssm_parameter_name = "/cryptiq/GEMINI_API_KEY"
}

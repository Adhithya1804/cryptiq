variable "aws_region" {
  type        = string
  description = "AWS region to deploy resources in"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Project name tag and resource prefix"
  default     = "CRYPTIQ"
}

variable "environment" {
  type        = string
  description = "Deployment environment name (e.g. demo, staging, prod)"
  default     = "demo"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type for the CRYPTIQ host (t3.medium recommended for 2 vCPU / 4 GiB)"
  default     = "t3.medium"
  validation {
    condition     = contains(["t3.small", "t3.medium", "t3.large"], var.instance_type)
    error_message = "Instance type must be one of: t3.small, t3.medium, t3.large."
  }
}

variable "allowed_cidr" {
  type        = string
  description = "CIDR block permitted to reach HTTP port 80 (default 0.0.0.0/0)"
  default     = "0.0.0.0/0"
  validation {
    condition     = can(cidrnetmask(var.allowed_cidr))
    error_message = "allowed_cidr must be a valid IPv4 CIDR notation (e.g. 0.0.0.0/0 or 1.2.3.4/32)."
  }
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the dedicated demo VPC"
  default     = "10.20.0.0/16"
  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR notation."
  }
}

variable "subnet_cidr" {
  type        = string
  description = "CIDR block for the public subnet"
  default     = "10.20.1.0/24"
  validation {
    condition     = can(cidrnetmask(var.subnet_cidr))
    error_message = "subnet_cidr must be a valid IPv4 CIDR notation."
  }
}

variable "root_volume_size" {
  type        = number
  description = "Size of the encrypted root EBS volume in GiB"
  default     = 30
  validation {
    condition     = var.root_volume_size >= 20 && var.root_volume_size <= 100
    error_message = "root_volume_size must be between 20 and 100 GiB."
  }
}

variable "data_volume_size" {
  type        = number
  description = "Size of the encrypted persistent data EBS volume in GiB (mounted at /data for SQLite)"
  default     = 10
  validation {
    condition     = var.data_volume_size >= 5 && var.data_volume_size <= 50
    error_message = "data_volume_size must be between 5 and 50 GiB."
  }
}

variable "repo_url" {
  type        = string
  description = "Public git repository URL cloned on EC2 first boot"
  default     = "https://github.com/Adhithya1804/cryptiq.git"
}

variable "repo_ref" {
  type        = string
  description = "Git ref (branch, commit, or tag) to clone and deploy"
  default     = "aws-demo-deploy-layer"
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention in days (keep short for demo cost control)"
  default     = 3
  validation {
    condition     = contains([1, 3, 5, 7, 14], var.log_retention_days)
    error_message = "log_retention_days must be one of: 1, 3, 5, 7, 14."
  }
}

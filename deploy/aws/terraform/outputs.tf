output "public_ip" {
  description = "Public IPv4 address of the CRYPTIQ host"
  value       = aws_instance.cryptiq.public_ip
}

output "public_url" {
  description = "Public HTTP URL of the CRYPTIQ web interface"
  value       = "http://${aws_instance.cryptiq.public_ip}/"
}

output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.cryptiq.id
}

output "vpc_id" {
  description = "ID of the demo VPC"
  value       = aws_vpc.this.id
}

output "subnet_id" {
  description = "ID of the public subnet"
  value       = aws_subnet.public.id
}

output "security_group_id" {
  description = "ID of the security group"
  value       = aws_security_group.cryptiq.id
}

output "data_volume_id" {
  description = "ID of the encrypted persistent EBS volume (/data)"
  value       = aws_ebs_volume.data.id
}

output "ssm_session_command" {
  description = "SSM Session Manager command to connect to the instance shell (no SSH)"
  value       = "aws ssm start-session --target ${aws_instance.cryptiq.id} --region ${var.aws_region}"
}

output "ssm_refresh_command" {
  description = "Safe SSM command to refresh GEMINI_API_KEY from Parameter Store and restart backend without rebuilding"
  value       = "aws ssm send-command --instance-ids ${aws_instance.cryptiq.id} --region ${var.aws_region} --document-name 'AWS-RunShellScript' --parameters 'commands=[\"bash /opt/cryptiq/app/deploy/aws/scripts/refresh-secrets.sh\"]'"
}

output "cloudwatch_log_groups" {
  description = "CloudWatch log groups created for the stack"
  value       = [for lg in aws_cloudwatch_log_group.groups : lg.name]
}

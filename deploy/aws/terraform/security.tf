resource "aws_security_group" "cryptiq" {
  name        = "${local.name_prefix}-sg"
  description = "CRYPTIQ demo - public HTTP :80 only. SSH (:22) and app (:8000) are blocked."
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "Public HTTP demo frontend and nginx reverse proxy"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  egress {
    description = "Outbound egress for packages, GitHub archive, Gemini API, SSM, and CloudWatch"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.default_tags, {
    Name = "${local.name_prefix}-sg"
  })
}

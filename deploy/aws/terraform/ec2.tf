data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "cryptiq" {
  ami                         = data.aws_ssm_parameter.al2023_ami.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.cryptiq.id]
  iam_instance_profile        = aws_iam_instance_profile.instance.name
  associate_public_ip_address = true

  # Enforce IMDSv2 (Session Manager & security baseline requirement)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  # Encrypted root volume (OS + Docker cache)
  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size
    encrypted             = true
    delete_on_termination = true
    tags = merge(local.default_tags, {
      Name = "${local.name_prefix}-root-ebs"
    })
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    aws_region          = var.aws_region
    repo_url            = var.repo_url
    repo_ref            = var.repo_ref
    bootstrap_log_group = local.log_groups.bootstrap
  })
  user_data_replace_on_change = true

  tags = merge(local.default_tags, {
    Name = "${local.name_prefix}-instance"
  })

  depends_on = [
    aws_internet_gateway.this,
    aws_route_table_association.public,
    aws_iam_role_policy.instance,
    aws_cloudwatch_log_group.groups
  ]
}

# Dedicated encrypted EBS volume for SQLite database persistence
resource "aws_ebs_volume" "data" {
  availability_zone = aws_instance.cryptiq.availability_zone
  size              = var.data_volume_size
  type              = "gp3"
  encrypted         = true

  tags = merge(local.default_tags, {
    Name = "${local.name_prefix}-data-ebs"
  })
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.cryptiq.id
}

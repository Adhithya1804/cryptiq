resource "aws_cloudwatch_log_group" "groups" {
  for_each          = local.log_groups
  name              = each.value
  retention_in_days = var.log_retention_days
  tags              = local.default_tags
}

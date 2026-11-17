mock_provider "google" {}

variables {
  project_id                      = "cogniflow-demo-12345"
  billing_account_id              = "000000-000000-000000"
  project_number                  = "123456789012"
  budget_notification_channel_ids = ["projects/123456789012/notificationChannels/1"]
  github_repository               = "nhatminh06/personal-cognitive-load-monitor"
  master_authorized_networks = [{
    cidr_block   = "192.0.2.10/32"
    display_name = "qualification"
  }]
}

run "valid_bounded_inputs" {
  command = plan
}

run "reject_placeholder_project" {
  command = plan
  variables {
    project_id = "your-project"
  }
  expect_failures = [var.project_id]
}

run "reject_other_region" {
  command = plan
  variables {
    region = "us-east1"
  }
  expect_failures = [var.region]
}

run "reject_duplicate_zones" {
  command = plan
  variables {
    node_locations = ["us-central1-a", "us-central1-a"]
  }
  expect_failures = [var.node_locations]
}

run "reject_non_numeric_project_number" {
  command = plan
  variables {
    project_number = "project-number"
  }
  expect_failures = [var.project_number]
}

run "reject_missing_budget_channel" {
  command = plan
  variables {
    budget_notification_channel_ids = []
  }
  expect_failures = [var.budget_notification_channel_ids]
}

run "reject_public_control_plane_range" {
  command = plan
  variables {
    master_authorized_networks = [{
      cidr_block   = "0.0.0.0/0"
      display_name = "public"
    }]
  }
  expect_failures = [var.master_authorized_networks]
}

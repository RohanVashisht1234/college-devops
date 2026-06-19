variable "kubeconfig_path" {
  description = "Path to kubeconfig for Docker Desktop, Minikube, Kind, EKS, AKS, or GKE."
  type        = string
  default     = "~/.kube/config"
}

variable "namespace" {
  description = "Kubernetes namespace for platform resources."
  type        = string
  default     = "medgenome"
}

variable "grafana_admin_password" {
  description = "Initial Grafana admin password."
  type        = string
  sensitive   = true
  default     = "ChangeMe123!"
}

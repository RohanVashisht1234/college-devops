output "namespace" {
  value = kubernetes_namespace.medgenome.metadata[0].name
}

output "monitoring_note" {
  value = "Use kubectl port-forward in namespace ${var.namespace} to access Prometheus and Grafana."
}

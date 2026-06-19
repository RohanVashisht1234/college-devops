pipeline {
    agent any

    environment {
      PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
      IMAGE_NAME = 'medgenome-platform'
      IMAGE_TAG = "${env.BUILD_NUMBER}"
      KUBE_NAMESPACE = 'medgenome'
      PROJECT_DIR = '/Users/rohanvashisht/devops'
    }

    stages {
      stage('Tool Check') {
        steps {
          sh 'python3 --version'
          sh 'docker --version'
          sh 'kubectl version --client'
        }
      }

      stage('Install and Smoke Test') {
        steps {
          dir("${PROJECT_DIR}") {
            sh 'python3 -m venv .venv'
            sh '. .venv/bin/activate && pip install -r requirements.txt'
            sh '. .venv/bin/activate && python -m compileall app'
          }
        }
      }

      stage('Build Docker Image') {
        steps {
          dir("${PROJECT_DIR}") {
            sh 'docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .'
            sh 'docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${IMAGE_NAME}:latest'
          }
        }
      }

      stage('Deploy to Kubernetes') {
        steps {
          dir("${PROJECT_DIR}") {
            sh 'kubectl apply -f k8s/namespace.yaml'
            sh 'kubectl -n ${KUBE_NAMESPACE} apply -f k8s/'
            sh 'kubectl -n ${KUBE_NAMESPACE} rollout status deployment/medgenome-api'
          }
        }
      }
    }
  }

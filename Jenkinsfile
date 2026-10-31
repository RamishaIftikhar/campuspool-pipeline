pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                git branch: 'main', url: 'https://github.com/RamishaIftikhar/campuspool-pipeline.git'
                sh 'docker compose down'
                sh 'docker compose up -d'
            }
        }
    }
    post {
        always {
            script {
                sh "git config --global --add safe.directory ${env.WORKSPACE}"
                def committer = sh(script: "git log -1 --pretty=format:'%ae'", returnStdout: true).trim()
                emailext(
                    to: committer,
                    subject: "CampusPool build #${env.BUILD_NUMBER}: ${currentBuild.currentResult}",
                    body: "Build status: ${currentBuild.currentResult}\nJob: ${env.JOB_NAME}\nBuild URL: ${env.BUILD_URL}"
                )
            }
        }
    }
}

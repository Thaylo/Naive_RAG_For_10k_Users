#!/usr/bin/env python3

import yaml

# Read docker-compose.yml
with open('docker-compose.yml', 'r') as f:
    docker_compose = yaml.safe_load(f)

# Services to update (all except nginx)
services_to_update = [
    'master-task-db', 'chunk-config', 'upload', 
    'chunking-1', 'chunking-2', 'embedding-1', 
    'embedding-2', 'vectorial-db', 'rag-query'
]

# Update each service
for service_name in services_to_update:
    if service_name in docker_compose['services']:
        service = docker_compose['services'][service_name]
        
        # Add LOG_LEVEL environment variable
        if 'environment' not in service:
            service['environment'] = []
        if not any('LOG_LEVEL' in env for env in service['environment']):
            service['environment'].append('LOG_LEVEL=INFO')
        
        # Add logs volume
        if 'volumes' not in service:
            service['volumes'] = []
        if not any('/app/logs' in vol for vol in service['volumes']):
            service['volumes'].append('./logs:/app/logs')

# Write updated docker-compose.yml
with open('docker-compose.yml', 'w') as f:
    yaml.dump(docker_compose, f, default_flow_style=False, sort_keys=False)

print("docker-compose.yml updated with logging configuration for all services")
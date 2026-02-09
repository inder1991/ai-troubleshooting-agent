import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
from dataclasses import dataclass

@dataclass
class MetricResult:
    
    metric_name: str
    values: List[tuple[float,float]]
    labels: Dict[str,str]


class PrometheusMetricsAnalyzer:

    def __init__(self, prometheus_url:str, timeout: int =30):

        self.prometheus_url=prometheus_url.rstrip("/")
        self.timeout = timeout
        self.api_url = f"{prometheus_url}/api/v1"


    def query(self, query: str) -> Dict:

        try:
            response = requests.get(
                f"{self.api_url}/query",
                params={'query':query},
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.RequestException as e:
            raise Exception(f"failed to query prometheus: {str(e)}")
        
    def query_range(self, query: query, start: datetime,end: datetime, step: str = '1m' ) -> Dict:
        try:
            response = requests.get(

                f"{self.api_url}/query_range",
                params={
                    'query': query,
                    'start': start.timestamp(),
                    'end': end.timestamp(),
                    'step': step
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to query prometheus range: {str(e)}")

    
    def get_cpu_utilization(self, namespace: str, deployment: str, duration_minutes: int= 60) -> MetricResult:

        end =datetime.now()
        start = end - timedelta(minutes=duration_minutes)

        query = f'''
        rate(container_cpu_usage_seconds_total{{
                    namespace="{namespace}",
                    pod=~"{deployment}-.*",
                    container!="POD",
                    container!=""
                }}[5m]) * 100
                '''

        result = self.query_range(query,start,end, step ='1m')

        if result['status'] =='success' and result['data']['result']:
            metric_data = result['data']['result'][0]
            values = [(float(v[0]), float(v[1])) for v in metric_data['values']]
            return MetricResult(
                metric_name='cpu_utilization',
                values=values,
                labels=metric_data['metric']
            )

        return MetricResult('cpu_utilization', [], {})
    

    def get_memory_utilization(self, namespace: str, deployment: str, duration_minutes: int =60 ) -> MetricResult:

        end=datetime.now()
        start= end - timedelta(minutes=duration_minutes)


        query = f'''
        container_memory_working_set_bytes{{
            namespace="{namespace}",
            pod=~"{deployment}-.*",
            container!="POD",
            container!=""
        }} / 1024 / 1024
        '''

        result = self.query_range(query, start, end, step='1m')

        if result['status'] == 'success' and result['data']['result']:
            metric_data = result['data']['result'][0]
            values = [ (float(v[0]),float(v[1])) for v in result['data'][result]]
            return MetricResult(
                metric_name="memory_cutilization",
                values = values,
                labels = metric_data['metric']
            )
        return MetricResult('memory_utlization', [], {})

    def get_container_restarts(self, namespace: str, deployment: str) -> Dict[str, int]:
        """
        Get container restart counts for a deployment
        
        Args:
            namespace: Kubernetes namespace
            deployment: Deployment name
            
        Returns:
            Dictionary mapping pod names to restart counts
        """
        query = f'''
        kube_pod_container_status_restarts_total{{
            namespace="{namespace}",
            pod=~"{deployment}-.*"
        }}
        '''
        
        result = self.query(query)
        restart_counts = {}
        
        if result['status'] == 'success' and result['data']['result']:
            for metric in result['data']['result']:
                pod = metric['metric'].get('pod', 'unknown')
                restarts = int(float(metric['value'][1]))
                restart_counts[pod] = restarts
        
        return restart_counts
    
    def get_pod_status(self, namespace: str, deployment: str) -> Dict[str, List[str]]:
        """
        Get pod status information (Running, CrashLoopBackOff, etc.)
        
        Args:
            namespace: Kubernetes namespace
            deployment: Deployment name
            
        Returns:
            Dictionary categorizing pods by status
        """
        # Check for pods in various states
        statuses = {
            'running': [],
            'pending': [],
            'failed': [],
            'crashloopbackoff': [],
            'error': []
        }
        
        # Query for pod phase
        phase_query = f'''
        kube_pod_status_phase{{
            namespace="{namespace}",
            pod=~"{deployment}-.*"
        }}
        '''
        
        phase_result = self.query(phase_query)
        
        if phase_result['status'] == 'success' and phase_result['data']['result']:
            for metric in phase_result['data']['result']:
                pod = metric['metric'].get('pod', 'unknown')
                phase = metric['metric'].get('phase', 'unknown').lower()
                value = int(float(metric['value'][1]))
                
                if value == 1:  # Phase is active
                    if phase in statuses:
                        statuses[phase].append(pod)
        
        # Check for CrashLoopBackOff specifically
        crashloop_query = f'''
        kube_pod_container_status_waiting_reason{{
            namespace="{namespace}",
            pod=~"{deployment}-.*",
            reason="CrashLoopBackOff"
        }}
        '''
        
        crashloop_result = self.query(crashloop_query)
        
        if crashloop_result['status'] == 'success' and crashloop_result['data']['result']:
            for metric in crashloop_result['data']['result']:
                pod = metric['metric'].get('pod', 'unknown')
                if int(float(metric['value'][1])) == 1:
                    statuses['crashloopbackoff'].append(pod)
        
        return statuses
    
    def get_oom_kills(self, namespace: str, deployment: str) -> Dict[str, int]:
        """
        Get OOM (Out of Memory) kill counts for containers
        
        Args:
            namespace: Kubernetes namespace
            deployment: Deployment name
            
        Returns:
            Dictionary mapping container names to OOM kill counts
        """
        query = f'''
        kube_pod_container_status_terminated_reason{{
            namespace="{namespace}",
            pod=~"{deployment}-.*",
            reason="OOMKilled"
        }}
        '''
        
        result = self.query(query)
        oom_kills = {}
        
        if result['status'] == 'success' and result['data']['result']:
            for metric in result['data']['result']:
                container = metric['metric'].get('container', 'unknown')
                pod = metric['metric'].get('pod', 'unknown')
                key = f"{pod}/{container}"
                if int(float(metric['value'][1])) == 1:
                    oom_kills[key] = oom_kills.get(key, 0) + 1
        
        return oom_kills
    

    def get_resource_limits(self, namespace: str, deployment: str) -> Dict[str, Dict[str, float]]:
        """
        Get resource limits and requests for containers
        
        Args:
            namespace: Kubernetes namespace
            deployment: Deployment name
            
        Returns:
            Dictionary with resource limits and requests
        """
        resources = {}
        
        # CPU limits
        cpu_limit_query = f'''
        kube_pod_container_resource_limits{{
            namespace="{namespace}",
            pod=~"{deployment}-.*",
            resource="cpu"
        }}
        '''
        
        cpu_limit_result = self.query(cpu_limit_query)
        
        # Memory limits
        memory_limit_query = f'''
        kube_pod_container_resource_limits{{
            namespace="{namespace}",
            pod=~"{deployment}-.*",
            resource="memory"
        }} / 1024 / 1024
        '''
        
        memory_limit_result = self.query(memory_limit_query)
        
        # Process CPU limits
        if cpu_limit_result['status'] == 'success' and cpu_limit_result['data']['result']:
            for metric in cpu_limit_result['data']['result']:
                container = metric['metric'].get('container', 'unknown')
                if container not in resources:
                    resources[container] = {}
                resources[container]['cpu_limit'] = float(metric['value'][1])
        
        # Process memory limits
        if memory_limit_result['status'] == 'success' and memory_limit_result['data']['result']:
            for metric in memory_limit_result['data']['result']:
                container = metric['metric'].get('container', 'unknown')
                if container not in resources:
                    resources[container] = {}
                resources[container]['memory_limit_mb'] = float(metric['value'][1])
        
        return resources
    
    def analyze_deployment(self, namespace: str, deployment: str, 
                          duration_minutes: int = 60) -> Dict:
        """
        Comprehensive analysis of a deployment's metrics
        
        Args:
            namespace: Kubernetes namespace
            deployment: Deployment name
            duration_minutes: Time range for analysis in minutes
            
        Returns:
            Dictionary containing comprehensive metrics analysis
        """
        print(f"Analyzing metrics for {namespace}/{deployment}...")
        
        analysis = {
            'deployment': deployment,
            'namespace': namespace,
            'timestamp': datetime.now().isoformat(),
            'duration_minutes': duration_minutes,
            'metrics': {}
        }
        
        # Get CPU utilization
        cpu_data = self.get_cpu_utilization(namespace, deployment, duration_minutes)
        if cpu_data.values:
            cpu_values = [v[1] for v in cpu_data.values]
            analysis['metrics']['cpu'] = {
                'current': cpu_values[-1] if cpu_values else 0,
                'average': sum(cpu_values) / len(cpu_values),
                'max': max(cpu_values),
                'min': min(cpu_values),
                'data_points': len(cpu_values),
                'time_series': cpu_data.values
            }
        
        # Get memory utilization
        memory_data = self.get_memory_utilization(namespace, deployment, duration_minutes)
        if memory_data.values:
            memory_values = [v[1] for v in memory_data.values]
            analysis['metrics']['memory'] = {
                'current_mb': memory_values[-1] if memory_values else 0,
                'average_mb': sum(memory_values) / len(memory_values),
                'max_mb': max(memory_values),
                'min_mb': min(memory_values),
                'data_points': len(memory_values),
                'time_series': memory_data.values
            }
        
        # Get container restarts
        restarts = self.get_container_restarts(namespace, deployment)
        analysis['metrics']['restarts'] = restarts
        analysis['metrics']['total_restarts'] = sum(restarts.values())
        
        # Get pod status
        pod_status = self.get_pod_status(namespace, deployment)
        analysis['pod_status'] = pod_status
        
        # Get OOM kills
        oom_kills = self.get_oom_kills(namespace, deployment)
        analysis['metrics']['oom_kills'] = oom_kills
        
        # Get resource limits
        resource_limits = self.get_resource_limits(namespace, deployment)
        analysis['resource_limits'] = resource_limits
        
        # Generate health assessment
        analysis['health_assessment'] = self._assess_health(analysis)
        
        return analysis

      

    
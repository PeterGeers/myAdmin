"""
Scalability Workers

Contains the async processing and resource monitoring components:
- AsyncProcessingManager: Thread/process pool management for concurrent operations
- ResourceMonitor: System resource monitoring with alerting

Extracted from scalability_manager.py to separate monitoring/workers from
connection pooling and orchestration.
"""

import threading
import time
import queue
import os
import logging
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta

import psutil

logger = logging.getLogger(__name__)


class AsyncProcessingManager:
    """
    Async processing manager for handling concurrent operations.

    Features:
    - Multiple thread pools for different operation types
    - Queue-based task management
    - Batch processing capabilities
    - Resource-aware scaling
    """

    def __init__(self, config):
        self.config = config

        # Create thread pools
        self.io_executor = ThreadPoolExecutor(
            max_workers=config.io_thread_pool_size,
            thread_name_prefix="IO-Worker"
        )

        self.cpu_executor = ThreadPoolExecutor(
            max_workers=config.cpu_thread_pool_size,
            thread_name_prefix="CPU-Worker"
        )

        # Create process pool for CPU-intensive tasks
        self.process_executor = ProcessPoolExecutor(
            max_workers=min(4, os.cpu_count() or 1)
        )

        # Task queues
        self.io_queue = queue.Queue(maxsize=config.async_queue_size)
        self.cpu_queue = queue.Queue(maxsize=config.async_queue_size)

        # Statistics
        self.stats = {
            'io_tasks_processed': 0,
            'cpu_tasks_processed': 0,
            'batch_operations': 0,
            'avg_processing_time': 0.0,
            'queue_sizes': {'io': 0, 'cpu': 0}
        }

        self.stats_lock = threading.Lock()

        logger.info(f"🚀 Async Processing Manager initialized: "
                    f"IO Workers: {config.io_thread_pool_size}, "
                    f"CPU Workers: {config.cpu_thread_pool_size}")

    def submit_io_task(self, func: Callable, *args, **kwargs):
        """Submit I/O bound task to thread pool"""
        future = self.io_executor.submit(self._execute_with_stats, 'io', func, *args, **kwargs)
        return future

    def submit_cpu_task(self, func: Callable, *args, **kwargs):
        """Submit CPU bound task to thread pool"""
        future = self.cpu_executor.submit(self._execute_with_stats, 'cpu', func, *args, **kwargs)
        return future

    def submit_process_task(self, func: Callable, *args, **kwargs):
        """Submit CPU intensive task to process pool"""
        future = self.process_executor.submit(func, *args, **kwargs)
        return future

    def batch_process(self, items: List[Any], process_func: Callable,
                      batch_size: Optional[int] = None) -> List[Any]:
        """
        Process items in batches using thread pool.

        Args:
            items: List of items to process
            process_func: Function to apply to each item
            batch_size: Size of each batch (defaults to config value)

        Returns:
            List of processed results
        """
        if not items:
            return []

        batch_size = batch_size or self.config.batch_processing_size
        batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]

        start_time = time.time()
        results = []

        # Process batches concurrently
        futures = []
        for batch in batches:
            future = self.io_executor.submit(self._process_batch, batch, process_func)
            futures.append(future)

        # Collect results
        for future in futures:
            batch_results = future.result()
            results.extend(batch_results)

        # Update statistics
        processing_time = time.time() - start_time
        with self.stats_lock:
            self.stats['batch_operations'] += 1
            current_avg = self.stats['avg_processing_time']
            count = self.stats['batch_operations']
            self.stats['avg_processing_time'] = (current_avg * (count - 1) + processing_time) / count

        logger.debug(f"📦 Batch processed {len(items)} items in {processing_time:.3f}s")
        return results

    def _process_batch(self, batch: List[Any], process_func: Callable) -> List[Any]:
        """Process a single batch of items"""
        results = []
        for item in batch:
            try:
                result = process_func(item)
                results.append(result)
            except Exception as e:
                logger.error(f"❌ Batch processing error: {e}")
                results.append(None)
        return results

    def _execute_with_stats(self, task_type: str, func: Callable, *args, **kwargs):
        """Execute function and update statistics"""
        start_time = time.time()

        try:
            result = func(*args, **kwargs)

            with self.stats_lock:
                if task_type == 'io':
                    self.stats['io_tasks_processed'] += 1
                elif task_type == 'cpu':
                    self.stats['cpu_tasks_processed'] += 1

            return result

        except Exception as e:
            logger.error(f"❌ Task execution error ({task_type}): {e}")
            raise

        finally:
            processing_time = time.time() - start_time
            logger.debug(f"⚡ {task_type.upper()} task completed in {processing_time:.3f}s")

    def get_processing_statistics(self) -> Dict[str, Any]:
        """Get processing statistics"""
        with self.stats_lock:
            return {
                'thread_pools': {
                    'io_workers': self.config.io_thread_pool_size,
                    'cpu_workers': self.config.cpu_thread_pool_size,
                    'process_workers': self.process_executor._max_workers
                },
                'tasks_processed': {
                    'io_tasks': self.stats['io_tasks_processed'],
                    'cpu_tasks': self.stats['cpu_tasks_processed'],
                    'batch_operations': self.stats['batch_operations']
                },
                'performance': {
                    'avg_processing_time': self.stats['avg_processing_time'],
                    'queue_sizes': {
                        'io_queue': self.io_queue.qsize(),
                        'cpu_queue': self.cpu_queue.qsize()
                    }
                }
            }

    def shutdown(self):
        """Shutdown all executors gracefully"""
        logger.info("🔄 Shutting down async processing manager...")

        self.io_executor.shutdown(wait=True)
        self.cpu_executor.shutdown(wait=True)
        self.process_executor.shutdown(wait=True)

        logger.info("✅ Async processing manager shutdown complete")


class ResourceMonitor:
    """
    System resource monitor for auto-scaling decisions.

    Features:
    - CPU, Memory, and I/O monitoring
    - Performance trend analysis
    - Auto-scaling recommendations
    - Alert generation
    """

    def __init__(self, config):
        self.config = config
        self.monitoring_active = False
        self.monitoring_thread = None
        self.metrics_history = []
        self.alerts = []
        self.lock = threading.Lock()

        # Start monitoring
        self.start_monitoring()

    def start_monitoring(self):
        """Start resource monitoring"""
        if not self.monitoring_active:
            self.monitoring_active = True
            self.monitoring_thread = threading.Thread(target=self._monitor_resources, daemon=True)
            self.monitoring_thread.start()
            logger.info("📊 Resource monitoring started")

    def stop_monitoring(self):
        """Stop resource monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logger.info("📊 Resource monitoring stopped")

    def _monitor_resources(self):
        """Monitor system resources continuously"""
        while self.monitoring_active:
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')

                try:
                    network = psutil.net_io_counters()
                    network_stats = {
                        'bytes_sent': network.bytes_sent,
                        'bytes_recv': network.bytes_recv,
                        'packets_sent': network.packets_sent,
                        'packets_recv': network.packets_recv
                    }
                except Exception:
                    network_stats = {}

                process = psutil.Process()
                process_memory = process.memory_info()

                metrics = {
                    'timestamp': datetime.now(),
                    'cpu_percent': cpu_percent,
                    'memory': {
                        'total_gb': memory.total / (1024**3),
                        'available_gb': memory.available / (1024**3),
                        'percent_used': memory.percent,
                        'process_rss_mb': process_memory.rss / (1024**2),
                        'process_vms_mb': process_memory.vms / (1024**2)
                    },
                    'disk': {
                        'total_gb': disk.total / (1024**3),
                        'free_gb': disk.free / (1024**3),
                        'percent_used': (disk.total - disk.free) / disk.total * 100
                    },
                    'network': network_stats,
                    'process': {
                        'threads': process.num_threads(),
                        'connections': len(process.connections()) if hasattr(process, 'connections') else 0,
                        'cpu_percent': process.cpu_percent()
                    }
                }

                with self.lock:
                    self.metrics_history.append(metrics)

                    cutoff_time = datetime.now() - timedelta(hours=1)
                    self.metrics_history = [
                        m for m in self.metrics_history
                        if m['timestamp'] > cutoff_time
                    ]

                self._check_resource_alerts(metrics)

                time.sleep(self.config.monitoring_interval_seconds)

            except Exception as e:
                logger.error(f"❌ Resource monitoring error: {e}")
                time.sleep(self.config.monitoring_interval_seconds)

    def _check_resource_alerts(self, metrics: Dict[str, Any]):
        """Check if any resource thresholds are exceeded"""
        alerts = []

        if metrics['cpu_percent'] > self.config.resource_alert_threshold * 100:
            alerts.append({
                'type': 'cpu_high',
                'message': f"High CPU usage: {metrics['cpu_percent']:.1f}%",
                'severity': 'warning',
                'timestamp': datetime.now()
            })

        if metrics['memory']['percent_used'] > self.config.resource_alert_threshold * 100:
            alerts.append({
                'type': 'memory_high',
                'message': f"High memory usage: {metrics['memory']['percent_used']:.1f}%",
                'severity': 'warning',
                'timestamp': datetime.now()
            })

        if metrics['memory']['process_rss_mb'] > 1024:
            alerts.append({
                'type': 'process_memory_high',
                'message': f"High process memory: {metrics['memory']['process_rss_mb']:.1f}MB",
                'severity': 'info',
                'timestamp': datetime.now()
            })

        if alerts:
            with self.lock:
                self.alerts.extend(alerts)
                self.alerts = self.alerts[-100:]

            for alert in alerts:
                logger.warning(f"⚠️ Resource Alert: {alert['message']}")

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current resource metrics"""
        with self.lock:
            if self.metrics_history:
                return self.metrics_history[-1]
            return {}

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of resource metrics over time"""
        with self.lock:
            if not self.metrics_history:
                return {}

            cpu_values = [m['cpu_percent'] for m in self.metrics_history]
            memory_values = [m['memory']['percent_used'] for m in self.metrics_history]

            return {
                'time_range': {
                    'start': self.metrics_history[0]['timestamp'].isoformat(),
                    'end': self.metrics_history[-1]['timestamp'].isoformat(),
                    'data_points': len(self.metrics_history)
                },
                'cpu': {
                    'avg_percent': sum(cpu_values) / len(cpu_values),
                    'max_percent': max(cpu_values),
                    'min_percent': min(cpu_values)
                },
                'memory': {
                    'avg_percent': sum(memory_values) / len(memory_values),
                    'max_percent': max(memory_values),
                    'min_percent': min(memory_values)
                },
                'alerts': {
                    'total_alerts': len(self.alerts),
                    'recent_alerts': [
                        a for a in self.alerts
                        if a['timestamp'] > datetime.now() - timedelta(minutes=30)
                    ]
                }
            }

"""
Integration of AWS Notifications with existing monitoring systems
"""

import logging
from typing import Dict, Any
from datetime import datetime
from aws_notifications import get_notification_service

logger = logging.getLogger(__name__)


class NotificationIntegration:
    """
    Integrates AWS notifications with existing monitoring and alerting
    """
    
    def __init__(self):
        self.notification_service = get_notification_service()
        self.alert_cooldown = {}  # Prevent alert spam
        self.cooldown_minutes = 15
    
    def should_send_alert(self, alert_key: str) -> bool:
        """Check if enough time has passed since last alert of this type"""
        if alert_key not in self.alert_cooldown:
            return True
        
        last_sent = self.alert_cooldown[alert_key]
        minutes_passed = (datetime.now() - last_sent).total_seconds() / 60
        
        return minutes_passed >= self.cooldown_minutes
    
    def mark_alert_sent(self, alert_key: str):
        """Mark that an alert was sent"""
        self.alert_cooldown[alert_key] = datetime.now()
    
    def handle_resource_alert(self, alert: Dict[str, Any]) -> bool:
        """
        Handle resource alerts from scalability manager
        
        Args:
            alert: Alert dictionary with type, message, timestamp, severity
        """
        alert_type = alert.get('type', 'unknown')
        alert_key = f"resource_{alert_type}"
        
        if not self.should_send_alert(alert_key):
            logger.debug(f"Skipping alert {alert_key} - cooldown active")
            return False
        
        success = self.notification_service.send_alert(
            alert_type=f"Resource: {alert_type}",
            message=alert.get('message', 'Resource alert'),
            severity=alert.get('severity', 'WARNING'),
            details={
                'timestamp': alert.get('timestamp', datetime.now()).isoformat(),
                'type': alert_type
            }
        )
        
        if success:
            self.mark_alert_sent(alert_key)
        
        return success
    
    def handle_performance_alert(
        self,
        pool_name: str,
        avg_response_time: float,
        threshold: float
    ) -> bool:
        """Handle performance degradation alerts"""
        alert_key = f"performance_{pool_name}"
        
        if not self.should_send_alert(alert_key):
            return False
        
        success = self.notification_service.send_performance_alert(
            metric_name=f"Connection Pool: {pool_name}",
            current_value=avg_response_time,
            threshold=threshold,
            details=f"Response time has exceeded threshold. Consider scaling up."
        )
        
        if success:
            self.mark_alert_sent(alert_key)
        
        return success
    
    def handle_security_event(
        self,
        event_type: str,
        description: str,
        source_ip: str = None,
        user: str = None
    ) -> bool:
        """Handle security events"""
        return self.notification_service.send_security_alert(
            event_type=event_type,
            description=description,
            source_ip=source_ip,
            user=user
        )
    
    def notify_booking_received(self, booking_data: Dict[str, Any]) -> bool:
        """Notify when new booking is received"""
        return self.notification_service.send_business_notification(
            title="New Booking Received",
            message=f"A new booking has been received for {booking_data.get('listing', 'Unknown')}",
            data={
                'Guest': booking_data.get('guestName', 'N/A'),
                'Check-in': booking_data.get('checkinDate', 'N/A'),
                'Check-out': booking_data.get('checkoutDate', 'N/A'),
                'Channel': booking_data.get('channel', 'N/A'),
                'Amount': f"€{booking_data.get('amountGross', 0):.2f}"
            }
        )
    
    def notify_payment_received(self, payment_data: Dict[str, Any]) -> bool:
        """Notify when payment is received"""
        return self.notification_service.send_business_notification(
            title="Payment Received",
            message=f"Payment of €{payment_data.get('amount', 0):.2f} received",
            data=payment_data
        )
    
    def notify_report_generated(self, report_type: str, details: Dict[str, Any]) -> bool:
        """Notify when report is generated"""
        return self.notification_service.send_business_notification(
            title=f"{report_type} Report Generated",
            message=f"The {report_type} report has been generated successfully",
            data=details
        )
    
    def notify_error(self, error_type: str, error_message: str, stack_trace: str = None) -> bool:
        """Notify about application errors"""
        return self.notification_service.send_error_notification(
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace
        )


# Global instance
_integration: NotificationIntegration = None


def get_notification_integration() -> NotificationIntegration:
    """Get or create the global notification integration instance"""
    global _integration
    if _integration is None:
        _integration = NotificationIntegration()
    return _integration

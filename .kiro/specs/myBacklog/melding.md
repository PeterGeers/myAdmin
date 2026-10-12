CodeQL / Information exposure through an exception
In backend/src/routes/members_analytics_audit.py:

> +
+        record = log_analytics_output(
+            actor=user_email,
+            actor_roles=user_roles,
+            tenant=tenant,
+            output_kind=output_kind,
+            set_key=data.get("set_key"),
+            record_count=data.get("record_count"),
+            filter_summary=data.get("filter_summary"),
+        )
+
+        return jsonify({"success": True, "audit": record})
+
+    except Exception as e:  # noqa: BLE001 — route boundary: never leak a 500 stack
+        logger.error("Error recording analytics output audit: %s", e)
+        return jsonify({"error": "Failed to record audit", "message": str(e)}), 500
CodeQL / Information exposure through an exception
Stack trace information flows to this location and may be exposed to an external user.

Show more details

In backend/src/routes/members_mail.py:

> +                tenant,
+                audit_error,
+            )
+
+        return jsonify(
+            {
+                "success": True,
+                "message": "Email sent successfully",
+                "recipient_count": len(to_addresses),
+                "message_id": result.get("message_id"),
+            }
+        )
+
+    except Exception as e:  # noqa: BLE001 — route boundary: never leak a 500 stack
+        logger.error("Error mailing member set: %s", e)
+        return jsonify({"error": "Failed to send email", "message": str(e)}), 500
CodeQL / Information exposure through an exception
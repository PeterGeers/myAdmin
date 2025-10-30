def check_route_conflicts(app):
    """Check for duplicate routes across blueprints"""
    routes = {}
    conflicts = []
    
    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        route = str(rule)
        
        if route in routes:
            conflicts.append(f"CONFLICT: {route} -> {routes[route]} vs {endpoint}")
        else:
            routes[route] = endpoint
    
    if conflicts:
        print("⚠️  ROUTE CONFLICTS DETECTED:")
        for conflict in conflicts:
            print(f"   {conflict}")
        return False
    return True
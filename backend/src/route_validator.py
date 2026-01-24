def check_route_conflicts(app):
    """Check for duplicate routes across blueprints"""
    routes = {}
    conflicts = []
    
    for rule in app.url_map.iter_rules():
        endpoint = rule.endpoint
        route = str(rule)
        methods = tuple(sorted(rule.methods - {'HEAD', 'OPTIONS'}))  # Exclude HEAD and OPTIONS
        
        # Create a unique key combining route and methods
        route_key = (route, methods)
        
        if route_key in routes:
            conflicts.append(f"CONFLICT: {route} [{','.join(methods)}] -> {routes[route_key]} vs {endpoint}")
        else:
            routes[route_key] = endpoint
    
    if conflicts:
        print("WARNING: ROUTE CONFLICTS DETECTED:")
        for conflict in conflicts:
            print(f"   {conflict}")
        return False
    return True

def get_robot(robot_type='cmu', **kwargs):
    if robot_type == 'cmu':
        from .cmu_auto import CMUAutonomyBot
        return CMUAutonomyBot(**kwargs)
    elif robot_type == 'kuavo':
        from .kuavo_auto import KuavoAutonomyBot
        return KuavoAutonomyBot(**kwargs)
    else:
        raise ValueError(f'Invalid robot type: {robot_type}')


def create_robot(robot_type='cmu', **kwargs):
    """
    Create a robot instance based on the specified type.
    """
    if robot_type == 'cmu':
        from .cmu_auto import CMUAutonomyBot
        return CMUAutonomyBot(**kwargs)
    elif robot_type == 'kuavo':
        from .kuavo_auto import KuavoAutonomyBot
        return KuavoAutonomyBot(**kwargs)
    else:
        raise ValueError(f'Invalid robot type: {robot_type}')

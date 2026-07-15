_services = []

def service(cls):
    _services.append(cls)
    return cls


def get_services():
    return _services
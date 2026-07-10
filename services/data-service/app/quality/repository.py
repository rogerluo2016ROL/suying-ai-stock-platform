import uuid
_MEMORY = {}
def save(snapshot):
    sid = uuid.uuid4().hex
    _MEMORY[sid] = snapshot.to_dict(); _MEMORY[sid]['snapshot_id'] = sid
    return _MEMORY[sid]
def get(snapshot_id): return _MEMORY.get(snapshot_id)

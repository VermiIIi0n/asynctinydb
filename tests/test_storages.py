import ujson as json
import os
import random
import tempfile

import pytest

from asynctinydb import TinyDB, where
from asynctinydb.storages import JSONStorage, MemoryStorage, Storage, touch
from asynctinydb.table import Document

random.seed()

doc = {'none': [None, None], 'int': 42, 'float': 3.1415899999999999,
       'list': ['LITE', 'RES_ACID', 'SUS_DEXT'],
       'dict': {'hp': 13, 'sp': 5},
       'bool': [True, False, True, False]}

@pytest.mark.asyncio
async def test_json(tmpdir):
    # Write contents
    path = str(tmpdir.join('test.db'))
    storage = JSONStorage(path)
    await storage.write(doc)

    # Verify contents
    assert doc == await storage.read()
    await storage.close()

@pytest.mark.asyncio
async def test_json_kwargs(tmpdir):
    db_file = tmpdir.join('test.db')
    db = TinyDB(str(db_file), sort_keys=True, indent=4)

    # Write contents
    await db.insert({'b': 1})
    await db.insert({'a': 1})

    assert db_file.read() == '''{
    "_default": {
        "1": {
            "b": 1
        },
        "2": {
            "a": 1
        }
    }
}'''
    await db.close()

@pytest.mark.asyncio
async def test_json_readwrite(tmpdir):
    """
    Regression test for issue #1
    """
    path = str(tmpdir.join('test.db'))

    # Create TinyDB instance
    db = TinyDB(path, storage=JSONStorage)

    item = {'name': 'A very long entry'}
    item2 = {'name': 'A short one'}

    async def get(s):
        return (await db.get(where('name') == s))

    await db.insert(item)
    assert await get('A very long entry') == item

    await db.remove(where('name') == 'A very long entry')
    assert await get('A very long entry') is None

    await db.insert(item2)
    assert await get('A short one') == item2

    await db.remove(where('name') == 'A short one')
    assert await get('A short one') is None

    await db.close()

@pytest.mark.asyncio
async def test_json_read(tmpdir):
    r"""Open a database only for reading"""
    path = str(tmpdir.join('test.db'))
    with pytest.raises(FileNotFoundError):
        db = TinyDB(path, storage=JSONStorage, access_mode='r')
        await db.get(where('name') == '42')
    # Create small database
    db = TinyDB(path, storage=JSONStorage)
    await db.insert({'b': 1})
    await db.insert({'a': 1})
    await db.close()
    # Access in read mode
    db = TinyDB(path, storage=JSONStorage, access_mode='r')
    assert (await db.get(where('a') == 1)) == {'a': 1}  # reading is fine
    with pytest.raises(IOError):
        await db.insert({'c': 1})  # writing is not
    await db.close()

@pytest.mark.asyncio
async def test_create_dirs():
    temp_dir = tempfile.gettempdir()

    while True:
        dname = os.path.join(temp_dir, str(random.getrandbits(20)))
        if not os.path.exists(dname):
            db_dir = dname
            db_file = os.path.join(db_dir, 'db.json')
            break

    with pytest.raises(IOError):
        JSONStorage(db_file)

    await JSONStorage(db_file, create_dirs=True).close()
    assert os.path.exists(db_file)

    # Use create_dirs with already existing directory
    await JSONStorage(db_file, create_dirs=True).close()
    assert os.path.exists(db_file)

    os.remove(db_file)
    os.rmdir(db_dir)

@pytest.mark.asyncio
async def test_json_invalid_directory():
    with pytest.raises(IOError):
        async with TinyDB('/this/is/an/invalid/path/db.json', storage=JSONStorage):
            pass

@pytest.mark.asyncio
async def test_in_memory():
    # Write contents
    storage = MemoryStorage()
    await storage.write(doc)

    # Verify contents
    assert doc == await storage.read()

    # Test case for #21
    other = MemoryStorage()
    await other.write({})
    assert (await other.read()) != await storage.read()

@pytest.mark.asyncio
async def test_in_memory_close():
    async with TinyDB(storage=MemoryStorage) as db:
        await db.insert({})

def test_custom():
    # noinspection PyAbstractClass
    class MyStorage(Storage):
        pass

    with pytest.raises(TypeError):
        MyStorage()

@pytest.mark.asyncio
async def test_read_once():
    count = 0

    # noinspection PyAbstractClass
    class MyStorage(Storage):
        def __init__(self):
            self.memory = None

        async def read(self):
            nonlocal count
            count += 1

            return self.memory

        async def write(self, data):
            self.memory = data

    async with TinyDB(storage=MyStorage) as db:
        assert count == 0

        db.table(db.default_table_name)

        assert count == 0

        await db.all()

        assert count == 1

        await db.insert({'foo': 'bar'})

        assert count == 3  # One for getting the next ID, one for the insert

        await db.all()

        assert count == 4

@pytest.mark.asyncio
async def test_custom_with_exception():
    class MyStorage(Storage):
        async def read(self):
            pass

        async def write(self, data):
            pass

        def __init__(self):
            raise ValueError()

        async def close(self):
            raise RuntimeError()

    with pytest.raises(ValueError):
        async with TinyDB(storage=MyStorage) as db:
            pass

@pytest.mark.asyncio
async def test_yaml(tmpdir):
    """
    :type tmpdir: py._path.local.LocalPath
    """

    try:
        import yaml
    except ImportError:
        return pytest.skip('PyYAML not installed')

    def represent_doc(dumper, data):
        # Represent `Document` objects as their dict's string representation
        # which PyYAML understands
        return dumper.represent_data(dict(data))

    yaml.add_representer(Document, represent_doc)

    class YAMLStorage(Storage):
        def __init__(self, filename):
            self.filename = filename
            touch(filename, False)

        async def read(self):
            with open(self.filename) as handle:
                data = yaml.safe_load(handle.read())
                return data

        async def write(self, data):
            with open(self.filename, 'w') as handle:
                yaml.dump(data, handle)

        async def close(self):
            pass

    # Write contents
    path = str(tmpdir.join('test.db'))
    db = TinyDB(path, storage=YAMLStorage)
    await db.insert(doc)
    assert [doc] == await db.all()

    await db.update({'name': 'foo'})

    assert '!' not in tmpdir.join('test.db').read()

    assert await db.contains(where('name') == 'foo')
    assert len(db) == 1

@pytest.mark.asyncio
async def test_encoding(tmpdir):
    japanese_doc = {"Test": u"こんにちは世界"}

    path = str(tmpdir.join('test.db'))
    # cp936 is used for japanese encodings
    jap_storage = JSONStorage(path, encoding="cp936")
    await jap_storage.write(japanese_doc)

    try:
        exception = json.decoder.JSONDecodeError
    except AttributeError:
        exception = ValueError

    with pytest.raises(exception):
        # cp037 is used for english encodings
        eng_storage = JSONStorage(path, encoding="cp037")
        await eng_storage.read()

    jap_storage = JSONStorage(path, encoding="cp936")
    assert japanese_doc == await jap_storage.read()

@pytest.mark.asyncio
async def test_storage_event_hooks(tmpdir):
    data = {"ab": 42}

    path = str(tmpdir.join('test.db'))
    storage = JSONStorage(path)
    @storage.on.write.pre
    async def mul(ev: str, s: Storage, d: dict):
        d["ab"] *= 2  # should change 'ab' to 84
    @storage.on.write.post  # Make sure returning None won't overwrite the data
    async def no_return(*args):
        ...
    await storage.write(data)
    await storage.close()

    class EXC(Exception):
        ...
    with pytest.raises(EXC):
        storage = JSONStorage(path)
        @storage.on.read.pre
        async def r(*arg):
            raise EXC()
        await storage.read()

    storage = JSONStorage(path)
    @storage.on.read.post
    async def subs(ev: str, s: Storage, d: dict):
        d["ab"] -= 2  # should change 'ab' to 82
    assert {"ab": 82} == await storage.read()

    storage.event_hook.clear_actions()
    
    @storage.on.read.pre
    async def inject(ev, s, string):
        return "{\"ab\": 114}"
    assert {"ab": 114} == await storage.read()

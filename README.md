# skytest
云服务测试工具

环境要求:
```
python >= 3.6.0
```

## 编译 & 安装

1. 安装依赖包
    ```
    yum install -y glibc gcc python3-devel libvirt python-libvirt libvirt-devel
    pip3 install -r requirements.txt
    ```
2. 打包
    ```
    python3 -m pip wheel --prefer-binary --no-deps --wheel-dir=dist ./
    ```

3. 安装
    ```
    pip3 install -r dist/skytest-<version>-py3-none-any.whl
    ```

## 运行

1. 源码

    ```
    export PYTHONPATH=./
    cd src
    pdm run skytest/cmd/ecs_test.py action-test
    ```

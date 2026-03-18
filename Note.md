由于我发现,在使用这些软件的时候,有些功能并不是很清楚,所以我决定写一篇笔记来记录一下我的使用心得和一些常见问题的解决方法。

# GTK加python编译生成.exe的方法

``` bash
pip install pyinstaller
pyinstaller --onefile --windowed simplecalculator.py
```

如果更改之后需要重新编译生成.exe文件,可以使用以下命令:
先删除之前生成的build, dist, *.spec文件夹和文件,然后再执行上面的编译命令.
``` bash
Remove-Item build, dist, *.spec -Recurse -Force
```

# 让ai可以读取PDF的方法
pdfplumber是一个Python库,可以用来提取PDF文件中的文本和表格等内容。使用pdfplumber可以很方便地读取PDF文件并将其内容加载到AI的上下文中,以便进行分析和处理。
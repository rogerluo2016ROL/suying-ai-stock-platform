package com.ds.cockpit.screen.common.exception.file;

/**
 * 文件名称非法异常类
 * 
 * @author ruoyi
 */
public class FileNameUnlawfulException extends FileException
{
    private static final long serialVersionUID = 1L;

    public FileNameUnlawfulException()
    {
        super("upload.filename.unlawful", new Object[] { "包含非法字符" });
    }
}

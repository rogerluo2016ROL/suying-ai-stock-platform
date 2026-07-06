package com.ds.cockpit.screen.web.controller.common;

import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.net.URLDecoder;
import java.util.ArrayList;
import java.util.List;
import javax.annotation.security.PermitAll;
import javax.servlet.ServletOutputStream;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import com.ds.cockpit.screen.system.service.IGacEvaluationAnalysisService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import com.ds.cockpit.screen.common.config.RuoYiConfig;
import com.ds.cockpit.screen.common.constant.Constants;
import com.ds.cockpit.screen.common.core.domain.AjaxResult;
import com.ds.cockpit.screen.common.utils.StringUtils;
import com.ds.cockpit.screen.common.utils.file.FileUploadUtils;
import com.ds.cockpit.screen.common.utils.file.FileUtils;
import com.ds.cockpit.screen.framework.config.ServerConfig;

/**
 * 通用请求处理
 * 
 * @author ruoyi
 */

@RestController
@RequestMapping("/common")
public class CommonController
{
    private static final Logger log = LoggerFactory.getLogger(CommonController.class);

    @Autowired
    private ServerConfig serverConfig;

    private static final String FILE_DELIMETER = ",";

    @Autowired
    private IGacEvaluationAnalysisService gacEvaluationAnalysisService;

    /**
     * 通用下载请求
     * 
     * @param fileName 文件名称
     * @param delete 是否删除
     */
    @GetMapping("/download")
    public void fileDownload(String fileName, Boolean delete, HttpServletResponse response, HttpServletRequest request) throws Exception {
        gacEvaluationAnalysisService.checkArgument(request);
        log.info("通用下载请求");
        try
        {
            if (!FileUtils.checkAllowDownload(fileName))
            {
                throw new Exception(StringUtils.format("文件名称({})非法，不允许下载。 ", fileName));
            }
            String realFileName = System.currentTimeMillis() + fileName.substring(fileName.indexOf("_") + 1);
            String filePath = RuoYiConfig.getDownloadPath() + fileName;

            response.setContentType(MediaType.APPLICATION_OCTET_STREAM_VALUE);
            FileUtils.setAttachmentResponseHeader(response, realFileName);
            FileUtils.writeBytes(filePath, response.getOutputStream());
            if (delete)
            {
                FileUtils.deleteFile(filePath);
            }
        }
        catch (Exception e)
        {
            log.error("下载文件失败", e);
        }
    }

    @GetMapping("/preview")
    // @Operation(summary = "文件预览")
    public void getFilePreview(String fileName, HttpServletResponse response, HttpServletRequest request) throws Exception {
        gacEvaluationAnalysisService.checkArgument(request);
        log.info("文件预览请求-开始");
        try
        {
            if (!FileUtils.checkAllowDownload(fileName))
            {
                throw new Exception(StringUtils.format("文件名称({})非法，不允许下载。 ", fileName));
            }

            // 读取内容
            String filePath = RuoYiConfig.getDownloadPath() + fileName;
            File file = new File(filePath);
            if (!file.exists())
            {
                throw new FileNotFoundException(filePath);
            }
            FileInputStream fis = new FileInputStream(file);

            //文件路径
            BufferedInputStream inputStream = new BufferedInputStream(fis);
            ServletOutputStream outputStream = response.getOutputStream();

            //响应文件格式
            response.setContentType(this.getContentType(this.getSuffix(fileName)));

            int len = 0;
            byte[] bytes = new byte[1024];
            while ((len = inputStream.read(bytes)) != -1) {
                //读取输出流
                outputStream.write(bytes, 0, len);
            }
            outputStream.flush(); //刷新
            outputStream.close();
            inputStream.close();
            log.info("文件预览请求-结束");
        } catch (Exception e) {
            log.error("预览文件失败", e);
            e.printStackTrace();
        }
    }

    /**
     * 通用上传请求（单个）
     */
    @PostMapping("/upload")
    public AjaxResult uploadFile(MultipartFile file, HttpServletRequest request) throws Exception
    {
        gacEvaluationAnalysisService.checkArgument(request);
        log.info("通用上传请求（单个）");
        try
        {
            // 上传文件路径
            String filePath = RuoYiConfig.getUploadPath();
            // 上传并返回新文件名称
            String fileName = FileUploadUtils.upload(filePath, file);
            String url = serverConfig.getUrl() + fileName;
            AjaxResult ajax = AjaxResult.success();
            ajax.put("url", url);
            ajax.put("fileName", fileName);
            ajax.put("newFileName", FileUtils.getName(fileName));
            ajax.put("originalFilename", file.getOriginalFilename());
            return ajax;
        }
        catch (Exception e)
        {
            return AjaxResult.error(e.getMessage());
        }
    }

    /**
     * 通用上传请求（多个）
     */
    @PostMapping("/uploads")
    public AjaxResult uploadFiles(List<MultipartFile> files, HttpServletRequest request) throws Exception
    {
        gacEvaluationAnalysisService.checkArgument(request);
        log.info("通用上传请求（多个）-开始");
        try
        {
            // 上传文件路径
            String filePath = RuoYiConfig.getUploadPath();
            List<String> urls = new ArrayList<String>();
            List<String> fileNames = new ArrayList<String>();
            List<String> newFileNames = new ArrayList<String>();
            List<String> originalFilenames = new ArrayList<String>();
            for (MultipartFile file : files)
            {
                // 上传并返回新文件名称
                String fileName = FileUploadUtils.upload(filePath, file);
                String url = serverConfig.getUrl() + fileName;
                urls.add(url);
                fileNames.add(fileName);
                newFileNames.add(FileUtils.getName(fileName));
                originalFilenames.add(file.getOriginalFilename());
            }
            AjaxResult ajax = AjaxResult.success();
            ajax.put("urls", StringUtils.join(urls, FILE_DELIMETER));
            ajax.put("fileNames", StringUtils.join(fileNames, FILE_DELIMETER));
            ajax.put("newFileNames", StringUtils.join(newFileNames, FILE_DELIMETER));
            ajax.put("originalFilenames", StringUtils.join(originalFilenames, FILE_DELIMETER));
            log.info("通用上传请求（多个）-结束");
            return ajax;
        }
        catch (Exception e)
        {
            log.error("通用上传请求（多个）-上传失败");
            log.error(e.getCause().toString());
            log.error(e.getMessage());
            log.error(e.getLocalizedMessage());
            log.error(e.getStackTrace().toString());
            e.printStackTrace();
            return AjaxResult.error(e.getMessage()+"--"+e.getLocalizedMessage());
        }
    }

    /**
     * 本地资源通用下载
     */
    @GetMapping("/download/resource")
    public void resourceDownload(String resource, HttpServletRequest request, HttpServletResponse response)
            throws Exception
    {
        gacEvaluationAnalysisService.checkArgument(request);
        log.info("本地资源通用下载");
        try
        {
            if (!FileUtils.checkAllowDownload(resource))
            {
                throw new Exception(StringUtils.format("资源文件({})非法，不允许下载。 ", resource));
            }
            // 本地资源路径
            String localPath = RuoYiConfig.getProfile();
            // 数据库资源地址
            String downloadPath = localPath + StringUtils.substringAfter(resource, Constants.RESOURCE_PREFIX);
            // 下载名称
            String downloadName = StringUtils.substringAfterLast(downloadPath, "/");
            response.setContentType(MediaType.APPLICATION_OCTET_STREAM_VALUE);
            FileUtils.setAttachmentResponseHeader(response, downloadName);
            FileUtils.writeBytes(downloadPath, response.getOutputStream());
        }
        catch (Exception e)
        {
            log.error("下载文件失败", e);
        }
    }

    public String getContentType(String suffix) {
        String contentType = "";
        //转小写
        switch (suffix.toLowerCase()) {
            case "txt":
                contentType = "text/plain";
                break;
            case "html":
                contentType = "text/html";
                break;
            case "css":
                contentType = "text/css";
                break;
            case "js":
                contentType = "text/javascript";
                break;
            case "json":
                contentType = "application/json";
                break;
            case "xml":
                contentType = "application/xml";
                break;
            case "jpeg":
            case "jpg":
                contentType = "image/jpeg";
                break;
            case "png":
                contentType = "image/png";
                break;
            case "gif":
                contentType = "image/gif";
                break;
            case "mp3":
                contentType = "audio/mpeg";
                break;
            case "wav":
                contentType = "audio/wav";
                break;
            case "ogg":
                contentType = "audio/ogg";
                break;
            case "mp4":
                contentType = "video/mp4";
                break;
            case "webm":
                contentType = "video/webm";
                break;
            case "pdf":
                contentType = "application/pdf";
                break;
            case "tiff":
                contentType = "image/tiff";
                break;
            default:
                contentType = "application/octet-stream";
                break;
        }
        return contentType;
    }

    //获取文件后缀
    public String getSuffix(String filename) {
        int dotIndex = filename.lastIndexOf(".");
        return filename.substring(dotIndex + 1);
    }
}

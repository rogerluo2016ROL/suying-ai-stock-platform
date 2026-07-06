package com.ds.cockpit.screen.common.utils.security;

import com.ds.cockpit.screen.common.utils.mapper.JsonMapper;
import lombok.extern.slf4j.Slf4j;

import java.nio.charset.StandardCharsets;

/**
 * Legacy request/response encryption helper.
 *
 * <p>Do not keep RSA keys in source code. The standalone ChatBI app reads them
 * from environment variables only when this legacy helper is explicitly used.</p>
 */
@Slf4j
public class ParamsEncryptUtil {
    private static final String PUBLIC_KEY_ENV = "CHATBI_RSA_PUBLIC_KEY";
    private static final String PRIVATE_KEY_ENV = "CHATBI_RSA_PRIVATE_KEY";
    private static final String PUBLIC_KEY_2_ENV = "CHATBI_RSA_PUBLIC_KEY_2";
    private static final String PRIVATE_KEY_2_ENV = "CHATBI_RSA_PRIVATE_KEY_2";

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalStateException("Missing required env: " + name);
        }
        return value.trim();
    }

    public static String encryptData(String orginRespStr) {
        try {
            String aesKey = AesKeyGenerator.createAesKey(false);
            String aesSalt = AesKeyGenerator.createAesSalt();
            log.trace("明文orginRespStr={}", orginRespStr);
            String encryptData = AesCbc.encrypt(orginRespStr, aesKey, aesSalt);
            log.trace("密文encryptData={}", encryptData);
            String encryptKey = RsaEcb.encryptByPublicKey(
                    aesKey + AesKeyGenerator.AES_KEY_SALT_SEPERATOR + aesSalt,
                    requiredEnv(PUBLIC_KEY_ENV));
            log.trace("密钥密文encryptKey={}", encryptKey);
            EncryptVo encryptVo = new EncryptVo();
            encryptVo.setEncryptData(encryptData);
            encryptVo.setEncryptKey(encryptKey);
            return JsonMapper.toJson(encryptVo);
        } catch (Exception e) {
            log.info("ParamsEncryptUtil.encryptData,加密异常:{}", e.getMessage());
            return null;
        }
    }

    public static String decryptData(String encryptRequestBodyStr) throws Exception {
        EncryptVo encryptVo = JsonMapper.fromJson(encryptRequestBodyStr, EncryptVo.class);
        String encryptData = encryptVo.getEncryptData();
        String encryptKey = encryptVo.getEncryptKey();
        log.trace("密文orginRespStr={}", encryptData);
        String decryptAesKey = RsaEcb.decryptByPrivateKey(encryptKey, requiredEnv(PRIVATE_KEY_ENV));
        String[] aesKeyAarry = decryptAesKey.split(AesKeyGenerator.AES_KEY_SALT_SEPERATOR);
        byte[] decryptDataBytes = AesCbc.decrypt(encryptData, aesKeyAarry[0], aesKeyAarry[1]);
        String body = new String(decryptDataBytes, StandardCharsets.UTF_8);
        log.trace("明文encryptData={}", body);
        return body;
    }

    public static String encryptData2(String orginRespStr) throws Exception {
        String aesKey = AesKeyGenerator.createAesKey(false);
        String aesSalt = AesKeyGenerator.createAesSalt();
        log.trace("明文orginRespStr={}", orginRespStr);
        String encryptData = AesCbc.encrypt(orginRespStr, aesKey, aesSalt);
        log.trace("密文encryptData={}", encryptData);
        String encryptKey = RsaEcb.encryptByPublicKey(
                aesKey + AesKeyGenerator.AES_KEY_SALT_SEPERATOR + aesSalt,
                requiredEnv(PUBLIC_KEY_2_ENV));
        log.trace("密钥密文encryptKey={}", encryptKey);
        EncryptVo encryptVo = new EncryptVo();
        encryptVo.setEncryptData(encryptData);
        encryptVo.setEncryptKey(encryptKey);
        return JsonMapper.toJson(encryptVo);
    }

    public static String decryptData2(String encryptRequestBodyStr) throws Exception {
        EncryptVo encryptVo = JsonMapper.fromJson(encryptRequestBodyStr, EncryptVo.class);
        String encryptData = encryptVo.getEncryptData();
        String encryptKey = encryptVo.getEncryptKey();
        log.trace("密文orginRespStr={}", encryptData);
        String decryptAesKey = RsaEcb.decryptByPrivateKey(encryptKey, requiredEnv(PRIVATE_KEY_2_ENV));
        String[] aesKeyAarry = decryptAesKey.split(AesKeyGenerator.AES_KEY_SALT_SEPERATOR);
        byte[] decryptDataBytes = AesCbc.decrypt(encryptData, aesKeyAarry[0], aesKeyAarry[1]);
        String body = new String(decryptDataBytes, StandardCharsets.UTF_8);
        log.trace("明文encryptData={}", body);
        return body;
    }
}

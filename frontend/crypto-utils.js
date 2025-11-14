/**
 * 前端加密工具
 * 使用 AES-256-GCM 加密敏感数据
 */

// 使用 Web Crypto API 进行加密（现代浏览器支持）
class CryptoUtils {
    constructor() {
        // 从服务器获取的加密密钥（通过非敏感接口获取）
        this.encryptionKey = null;
        this.keyDerivationSalt = null;
        this.keyId = null; // 临时密钥ID
        this.keyExpiresAt = null; // 密钥过期时间
    }

    /**
     * 初始化加密密钥
     * 从服务器获取公钥或通过密钥交换协议获取
     */
    async initializeKey(forceRefresh = false) {
        try {
            // 如果已有密钥且未强制刷新，直接返回
            if (this.encryptionKey && !forceRefresh && this.keyId && this.keyExpiresAt > Date.now()) {
                return true;
            }
            
            // 方案1: 从服务器获取临时加密密钥（推荐用于登录等敏感操作）
            const apiBaseUrl = window.APP_CONFIG?.api?.baseUrl || '/api/v1';
            const keyUrl = `${apiBaseUrl}/auth/encryption-key`;
            
            try {
                const response = await fetch(keyUrl, {
                    method: 'GET',
                    credentials: 'include'
                });
                
                
                if (response.ok) {
                    const data = await response.json();
                    
                    if (data.success && data.data && data.data.key) {
                        // 使用服务器返回的临时密钥
                        const keyData = this.base64ToArrayBuffer(data.data.key);
                        this.encryptionKey = await crypto.subtle.importKey(
                            'raw',
                            keyData,
                            { name: 'AES-GCM' },
                            false,
                            ['encrypt']
                        );
                        this.keyId = data.data.key_id;
                        this.keyExpiresAt = Date.now() + (data.data.expires_in * 1000);
                        this.keyDerivationSalt = data.data.salt ? this.base64ToArrayBuffer(data.data.salt) : null;
                        return true;
                    } else {
                        console.warn('[CryptoUtils] ⚠️ 密钥接口返回数据格式不正确:', data);
                    }
                } else {
                    const errorText = await response.text();
                    console.warn('[CryptoUtils] ⚠️ 密钥接口请求失败:', response.status, errorText);
                }
            } catch (fetchError) {
                console.warn('[CryptoUtils] ⚠️ 获取密钥时网络错误:', fetchError);
            }
            
            // 方案2: 使用固定密钥（从配置或环境变量获取，仅用于开发环境）
            // 生产环境应该使用方案1
            console.warn('[CryptoUtils] ⚠️ 无法从服务器获取密钥，降级使用固定密钥（仅用于开发环境）');
            const fixedKey = window.APP_CONFIG?.security?.encryptionKey || 'default-encryption-key-32-bytes!!';
            const keyData = new TextEncoder().encode(fixedKey.padEnd(32, '0').slice(0, 32));
            this.encryptionKey = await crypto.subtle.importKey(
                'raw',
                keyData,
                { name: 'AES-GCM' },
                false,
                ['encrypt']
            );
            this.keyId = null; // 固定密钥没有key_id
            return true;
        } catch (error) {
            console.error('初始化加密密钥失败:', error);
            return false;
        }
    }

    /**
     * 加密数据
     * @param {string|object} data - 要加密的数据
     * @returns {Promise<{encrypted_data: string, key_id?: string}>} 加密数据和可选的密钥ID
     */
    async encrypt(data) {
        try {
            // 确保密钥已初始化
            if (!this.encryptionKey) {
                const initialized = await this.initializeKey();
                if (!initialized) {
                    throw new Error('加密密钥初始化失败');
                }
            }
            
            // 检查密钥是否过期
            if (this.keyExpiresAt && this.keyExpiresAt <= Date.now()) {
                const refreshed = await this.initializeKey(true);
                if (!refreshed) {
                    throw new Error('加密密钥刷新失败');
                }
            }

            // 将数据转换为字符串
            const dataString = typeof data === 'string' ? data : JSON.stringify(data);
            const dataBuffer = new TextEncoder().encode(dataString);

            // 生成随机IV（初始化向量）
            const iv = crypto.getRandomValues(new Uint8Array(12));

            // 加密
            const encryptedData = await crypto.subtle.encrypt(
                {
                    name: 'AES-GCM',
                    iv: iv,
                    tagLength: 128
                },
                this.encryptionKey,
                dataBuffer
            );

            // 组合 IV + 加密数据
            const combined = new Uint8Array(iv.length + encryptedData.byteLength);
            combined.set(iv, 0);
            combined.set(new Uint8Array(encryptedData), iv.length);

            // 返回加密数据和密钥ID（如果使用临时密钥）
            const result = {
                encrypted_data: this.arrayBufferToBase64(combined)
            };
            if (this.keyId) {
                result.key_id = this.keyId;
            }
            return result;
        } catch (error) {
            console.error('加密失败:', error);
            throw error;
        }
    }

    /**
     * 解密数据（前端通常不需要，主要用于测试）
     * @param {string} encryptedData - Base64编码的加密数据
     * @returns {Promise<string>} 解密后的数据
     */
    async decrypt(encryptedData) {
        try {
            if (!this.encryptionKey) {
                throw new Error('加密密钥未初始化');
            }

            const combined = this.base64ToArrayBuffer(encryptedData);
            const iv = combined.slice(0, 12);
            const data = combined.slice(12);

            const decryptedData = await crypto.subtle.decrypt(
                {
                    name: 'AES-GCM',
                    iv: iv,
                    tagLength: 128
                },
                this.encryptionKey,
                data
            );

            return new TextDecoder().decode(decryptedData);
        } catch (error) {
            console.error('解密失败:', error);
            throw error;
        }
    }

    /**
     * Base64 转 ArrayBuffer
     */
    base64ToArrayBuffer(base64) {
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        return bytes.buffer;
    }

    /**
     * ArrayBuffer 转 Base64
     */
    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }
}

// 创建全局实例
window.cryptoUtils = new CryptoUtils();

// 兼容旧浏览器的简化版本（使用 CryptoJS，需要引入库）
if (typeof crypto === 'undefined' || !crypto.subtle) {
    console.warn('浏览器不支持 Web Crypto API，将使用简化加密方案');
    
    // 降级方案：使用简单的 Base64 编码（仅用于开发，生产环境应使用 HTTPS）
    window.cryptoUtils = {
        async encrypt(data) {
            const dataString = typeof data === 'string' ? data : JSON.stringify(data);
            // 返回与标准格式一致的对象，包含 encrypted_data 字段
            const encryptedData = btoa(encodeURIComponent(dataString));
            return {
                encrypted_data: encryptedData
            };
        },
        async decrypt(encryptedData) {
            try {
                // 如果传入的是对象，提取 encrypted_data 字段
                const data = typeof encryptedData === 'string' 
                    ? encryptedData 
                    : encryptedData.encrypted_data || encryptedData;
                return decodeURIComponent(atob(data));
            } catch (e) {
                throw new Error('解密失败');
            }
        },
        async initializeKey() {
            return true;
        }
    };
}


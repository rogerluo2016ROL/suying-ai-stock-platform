package com.ds.cockpit.screen.system.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.ds.cockpit.screen.common.core.domain.entity.SystemUserNoviceGuideEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemUserNoviceGuideVo;

/**
 * @Author: ZhouHong
 * @description 针对表【system_user_novice_guide】的数据库操作Service
 * @Date: 2024-02-01 下午 01:39
 */
public interface SystemUserNoviceGuideService {

    boolean loginFirst(SystemUserNoviceGuideVo systemUserNoviceGuideVo);

    boolean resetLogin(SystemUserNoviceGuideVo systemUserNoviceGuideVo);
}

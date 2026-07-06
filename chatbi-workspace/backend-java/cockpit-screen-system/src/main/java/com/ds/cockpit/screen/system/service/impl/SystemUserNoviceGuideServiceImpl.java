package com.ds.cockpit.screen.system.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.ds.cockpit.screen.common.core.domain.entity.SystemUserNoviceGuideEntity;
import com.ds.cockpit.screen.common.core.domain.entity.vo.SystemUserNoviceGuideVo;
import com.ds.cockpit.screen.system.mapper.SystemUserNoviceGuideMapper;
import com.ds.cockpit.screen.system.service.SystemUserNoviceGuideService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.Date;

/**
* @author zhouhong
* @description 针对表【system_user_novice_guide】的数据库操作Service实现
* @createDate 2024-02-01 下午 01:39
*/
@Service
public class SystemUserNoviceGuideServiceImpl implements SystemUserNoviceGuideService {

    @Autowired
    private SystemUserNoviceGuideMapper systemUserNoviceGuideMapper;

    @Override
    public boolean loginFirst(SystemUserNoviceGuideVo systemUserNoviceGuideVo) {
        //先查询
        SystemUserNoviceGuideEntity userNoviceGuideEntity  = systemUserNoviceGuideMapper.getSystemUserNoviceGuide(systemUserNoviceGuideVo);
        // 否，再存数据
        if(null == userNoviceGuideEntity){
            userNoviceGuideEntity = new SystemUserNoviceGuideEntity();
            userNoviceGuideEntity.setUserId(systemUserNoviceGuideVo.getUserId());
            userNoviceGuideEntity.setUserName(systemUserNoviceGuideVo.getUserName());
            userNoviceGuideEntity.setUserDept(systemUserNoviceGuideVo.getUserDept());
            userNoviceGuideEntity.setDescriptions(systemUserNoviceGuideVo.getDescriptions());
            int insert = systemUserNoviceGuideMapper.insertEntity(userNoviceGuideEntity);
            if(insert > 0){
               return true;
            }
        }
        return false;
    }

    @Override
    public boolean resetLogin(SystemUserNoviceGuideVo systemUserNoviceGuideVo) {
        // 先查询
        SystemUserNoviceGuideEntity userNoviceGuideEntity  = systemUserNoviceGuideMapper.getSystemUserNoviceGuide(systemUserNoviceGuideVo);
        // 有，再更新删除标识
        if(null != userNoviceGuideEntity){
            // userNoviceGuideEntity.setAvailability(0);
            // userNoviceGuideEntity.setUpdateTime(new Date());
            int updateById = systemUserNoviceGuideMapper.unAvailability(userNoviceGuideEntity.getId());
            if(updateById > 0){
                return true;
            }
        }
        return false;
    }
}





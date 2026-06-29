import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Diagnosis from '../pages/Diagnosis'
import Training from '../pages/Training'
import ModelRegistry from '../pages/ModelRegistry'
import RuntimeStatus from '../pages/RuntimeStatus'
import PlatformUpgrade from '../pages/PlatformUpgrade'

function renderPage(page: React.ReactNode, route: string) {
  return render(<MemoryRouter initialEntries={[route]}>{page}</MemoryRouter>)
}

describe('Phase 5 system pages', () => {
  it('renders diagnosis as concrete five-dimension analysis', () => {
    renderPage(<Diagnosis />, '/diagnosis/overview')

    expect(screen.getByRole('heading', { name: '个股诊断 - 综合诊断' })).toBeInTheDocument()
    expect(screen.getByText('五维评分')).toBeInTheDocument()
    expect(screen.queryByText('个股诊断骨架')).not.toBeInTheDocument()
  })

  it('renders model training and registry without skeleton copy', () => {
    renderPage(<Training />, '/training/tasks')
    expect(screen.getByRole('heading', { name: '模型训练 - 训练任务' })).toBeInTheDocument()
    expect(screen.getByText('训练任务队列')).toBeInTheDocument()
    expect(screen.queryByText('模型训练骨架')).not.toBeInTheDocument()

    renderPage(<ModelRegistry />, '/model-registry')
    expect(screen.getByRole('heading', { name: '模型注册 - 版本治理' })).toBeInTheDocument()
    expect(screen.getByText('生产模型注册表')).toBeInTheDocument()
    expect(screen.queryByText('模型注册骨架')).not.toBeInTheDocument()
  })

  it('renders runtime and platform upgrade governance views', () => {
    renderPage(<RuntimeStatus />, '/runtime')
    expect(screen.getByText('服务健康矩阵')).toBeInTheDocument()

    renderPage(<PlatformUpgrade />, '/platform-upgrade')
    expect(screen.getByText('多租户升级矩阵')).toBeInTheDocument()
    expect(screen.getByText('公共数据 / 私有对象边界')).toBeInTheDocument()
  })
})
